import requests
import keen
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.contrib.auth.models import User

from raven.contrib.django.raven_compat.models import client as raven_client

from app.celery_base import celery_app, CaptureFailure
from .utils import url_join


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def send_email_async(self, **kwargs):
    try:
        send_mail(**kwargs)
    except:
        raven_client.captureException()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def update_intercom_tags(self, email, attribute_id, attribute_value):
    if settings.INTERCOM_ACCESS_TOKEN:
        headers = {
            'Authorization': 'Bearer {}'.format(settings.INTERCOM_ACCESS_TOKEN),
            'Accept': 'application/json'
        }
        url = 'https://api.intercom.io/users'

        data = {
            "email": email,
            "custom_attributes": {
                attribute_id: attribute_value
            }
        }
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
        except:
            raven_client.captureException()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def update_baremetrics_attributes(self, email, attribute_id, attribute_value):
    if settings.BAREMETRICS_API_KEY:
        headers = {
            'Authorization': 'Bearer {}'.format(settings.BAREMETRICS_API_KEY),
            'Accept': 'application/json'
        }
        url = 'https://api.baremetrics.com/v1/attributes'
        data = {
            "attributes": [{
                "customer_email": email,
                "field_id": attribute_id,
                "value": attribute_value
            }]
        }

        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
        except:
            raven_client.captureException()


# TODO: Remove this task
@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=30)
def keen_add_event(self, event_name, event_data):
    keen_order_event(event_name, event_data)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=30)
def keen_order_event(self, event_name, event_data):
    try:
        try:
            if 'product' in event_data:
                cache_key = 'keen_event_product_price_{}'.format(event_data.get('product'))
                product_price = cache.get(cache_key)

                if product_price is None:
                    supplier_type = 'aliexpress'
                    if event_data.get('supplier_type'):
                        supplier_type = event_data.get('supplier_type')
                    url = url_join(settings.PRICE_MONITOR_HOSTNAME, '/api', supplier_type, '/products/price/', event_data.get('product'))
                    prices_response = requests.get(
                        url=url,
                        auth=(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD),
                        timeout=10,
                    )

                    product_price = prices_response.json()['price']
                    cache.set(cache_key, product_price, timeout=3600)

                if product_price:
                    event_data['product_price'] = product_price
        except:
            pass

        keen.add_event(event_name, event_data)
    except:
        raven_client.captureException(level='warning')


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=30)
def keen_send_event(self, event_name, event_data):
    try:
        if not settings.DEBUG and settings.KEEN_PROJECT_ID:
            keen.add_event(event_name, event_data)
    except:
        raven_client.captureException(level='warning')


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def export_user_activity(self, user_id, requester_id):
    from leadgalaxy.management.commands.user_activity_log import generate_user_activity
    from shopified_core.utils import send_email_from_template

    try:
        user = User.objects.get(id=int(user_id))
    except ValueError:
        user = User.objects.get(email__iexact=user_id)

    url = generate_user_activity(user)

    requester = User.objects.get(id=requester_id)
    send_email_from_template(
        tpl=f'Activity for {user.email} has been exported:\n{url}',
        subject='[Dropified] User Activity Export',
        recipient=requester.email
    )
