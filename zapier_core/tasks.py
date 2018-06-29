from __future__ import absolute_import

import json
import requests
import urlparse

from django.conf import settings
from raven.contrib.django.raven_compat.models import client as raven_client
from app.celery import celery_app, CaptureFailure, retry_countdown

from shopified_core.utils import http_exception_response


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def deliver_hook(self, target, payload, instance_id=None, hook_id=None, **kwargs):
    """
    target:     the url to receive the payload.
    payload:    a python primitive data structure
    instance_id:   a possibly None "trigger" instance ID
    hook_id:       the ID of defining Hook object
    """
    try:
        response = requests.post(
            url=target,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        response.raise_for_status()
    except Exception as e:
        raven_client.captureException(extra=http_exception_response(e))
        if not self.request.called_directly:
            countdown = retry_countdown('retry_deliver_hook_{}_{}'.format(hook_id, instance_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=5)


def deliver_hook_wrapper(target, payload, instance, hook):
    # instance is None if using custom event, not built-in
    if instance is not None:
        instance_id = instance.id
    else:
        instance_id = None
    if hook.event in settings.PRICE_MONITOR_EVENTS or hook.event == 'shopify_order_created':
        # If the event is one of price monitor events
        # and the hook needs to be triggered for specific product only,
        # then data needs to be checked to decide if the event is for specific product or not
        # https://hooks.zapier.com/hooks/standard/xxx/xxxxx/?store_type=shopify&store_id=1&product_id=10
        payload = payload.get('data', {})
        parsed = urlparse.urlparse(target)
        params = urlparse.parse_qs(parsed.query)
        if params.get('store_type') and params.get('store_type')[0] != payload.get('store_type'):
            return
        if params.get('store_id') and params.get('store_id')[0] != str(payload.get('store_id')):
            return
        if params.get('product_id') and params.get('product_id')[0] != str(payload.get('product_id')):
            return
        parsed = parsed._replace(query=None)
        target = urlparse.urlunparse(parsed)
    deliver_hook.apply_async(args=[target, payload, instance_id, hook.id])
