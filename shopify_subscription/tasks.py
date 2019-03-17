

import arrow
from app.celery_base import celery_app, CaptureFailure

from shopify_subscription.models import BaremetricsCustomer
from shopify_subscription.utils import BaremetricsRequest


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def cancel_baremetrics_subscriptions(self, baremetrics_customer_id=None):
    if baremetrics_customer_id is None:
        return

    customer = BaremetricsCustomer.objects.get(pk=baremetrics_customer_id)
    # Only cancel subscriptions if store is uninstalled
    if customer.store.is_active or customer.store.uninstalled_at is None:
        return

    baremetrics = BaremetricsRequest()
    data = {
        'canceled_at': arrow.get().timestamp
    }

    for subscription in customer.subscriptions.filter(canceled_at=None):
        url = '{}/subscriptions/{}/cancel'.format('{source_id}', subscription.subscription_oid)
        baremetrics.put(url, data=data)
