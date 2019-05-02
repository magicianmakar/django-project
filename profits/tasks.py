import arrow
from raven.contrib.django.raven_compat.models import client as raven_client
from app.celery_base import celery_app, CaptureFailure

from groovekart_core.models import GrooveKartStore

from . import utils
from . import models


@celery_app.task(bind=True, base=CaptureFailure)
def fetch_facebook_insights(self, store_id, store_type, facebook_access_ids):
    if store_type == 'gkart':
        store = GrooveKartStore.objects.get(pk=store_id)

    try:
        for access in models.FacebookAccess.objects.filter(id__in=facebook_access_ids):
            utils.get_facebook_ads(access.id)

        store.pusher_trigger('facebook-insights', {
            'success': True
        })
    except Exception:
        raven_client.captureException()

        store.pusher_trigger('facebook-insights', {
            'success': False,
            'error': 'Facebook API Error',
        })


@celery_app.task(bind=True, base=CaptureFailure)
def sync_gkart_store_profits(self, sync_id, store_id):
    sync = models.ProfitSync.objects.get(pk=sync_id)
    store = GrooveKartStore.objects.get(pk=store_id)

    api_url = store.get_api_url('orders.json')

    limit = 100
    page = 1

    while True:
        r = store.request.post(api_url, json={
            'limit': limit, 'offset': limit * (page - 1),
            'order_by': 'date_add', 'order_way': 'DESC'
        })

        result = r.json()
        # Empty list usually means we reached the end
        if 'Error' in result:
            break

        for order in result['orders']:
            models.ProfitOrder.objects.update_or_create(
                sync=sync,
                order_id=order.get('id'),
                defaults={
                    'date': arrow.get(order.get('created_at')).datetime,
                    'order_name': order.get('reference'),
                    'amount': order.get('total_price'),
                    'items': [f'{i.get("quantity", 1)} x {i.get("name")}' for i in order.get('line_items', [])],
                }
            )

        # Lesser results than limit means we reached the end
        if len(result['orders']) < limit:
            break
        page += 1
    sync.save()  # Update last_sync
