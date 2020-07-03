import json
import arrow

from lib.exceptions import capture_exception
from app.celery_base import celery_app, CaptureFailure

from groovekart_core.models import GrooveKartStore
from bigcommerce_core.models import BigCommerceStore
from woocommerce_core.models import WooStore
from commercehq_core.models import CommerceHQStore

from . import utils
from . import models


@celery_app.task(bind=True, base=CaptureFailure)
def fetch_facebook_insights(self, store_id, store_type, facebook_access_ids):
    if store_type == 'gkart':
        store = GrooveKartStore.objects.get(pk=store_id)
    elif store_type == 'bigcommerce':
        store = BigCommerceStore.objects.get(pk=store_id)
    elif store_type == 'woo':
        store = WooStore.objects.get(pk=store_id)
    elif store_type == 'chq':
        store = CommerceHQStore.objects.get(pk=store_id)

    try:
        for access in models.FacebookAccess.objects.filter(id__in=facebook_access_ids):
            utils.get_facebook_ads(access.id)

        store.pusher_trigger('facebook-insights', {
            'success': True
        })
    except Exception:
        capture_exception()

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
            if order.get('created_at') and order.get('created_at') != '0000-00-00 00:00:00':
                models.ProfitOrder.objects.update_or_create(
                    sync=sync,
                    order_id=order.get('id'),
                    defaults={
                        'date': arrow.get(order.get('created_at')).datetime,
                        'order_name': order.get('reference'),
                        'amount': order.get('total_price'),
                        'items': json.dumps([f'{i.get("quantity", 1)} x {i.get("name")}' for i in order.get('line_items', [])]),
                    }
                )

        # Lesser results than limit means we reached the end
        if len(result['orders']) < limit:
            break
        page += 1
    sync.save()  # Update last_sync


@celery_app.task(bind=True, base=CaptureFailure)
def sync_bigcommerce_store_profits(self, sync_id, store_id):
    sync = models.ProfitSync.objects.get(pk=sync_id)
    store = BigCommerceStore.objects.get(pk=store_id)

    r = store.request.get(
        url=store.get_api_url('v2/orders'),
    )
    r.raise_for_status()

    orders = r.json()

    for order in orders:
        if order.get('date_created') and order.get('date_created') != '0000-00-00 00:00:00':
            req_product = store.request.get(
                url=store.get_api_url('v2/orders/{}/products'.format(order['id']))
            )
            req_product.raise_for_status()
            line_items = req_product.json()
            req_transactions = store.request.get(
                url=store.get_api_url('v3/orders/{}/transactions'.format(order['id']))
            )
            req_transactions.raise_for_status()
            data = req_transactions.json().get('data')

            models.ProfitOrder.objects.update_or_create(
                sync=sync,
                order_id=order.get('id'),
                defaults={
                    'date': arrow.get(order['date_created'], 'ddd, D MMM YYYY HH:mm:ss Z').format('YYYY-MM-DD HH:mm'),
                    'order_name': order.get('id'),
                    'amount': data[0].get('amount'),
                    'items': json.dumps([f'{i.get("quantity", 1)} x {i.get("name")}' for i in line_items]),
                }
            )
    sync.save()  # Update last sync


@celery_app.task(bind=True, base=CaptureFailure)
def sync_woocommerce_store_profits(self, sync_id, store_id):
    sync = models.ProfitSync.objects.get(pk=sync_id)
    store = WooStore.objects.get(pk=store_id)

    limit = 100
    page = 1

    while True:
        wcapi = store.get_wcapi()
        orders = wcapi.get('orders/', params={
            'per_page': limit,
            'page': page,
            'orderby': 'date'
        }).json()
        # Empty list usually means we reached the end
        if 'Error' in orders:
            break

        for order in orders:
            if order.get('date_created') and order.get('date_created') != '0000-00-00T00:00:00':
                models.ProfitOrder.objects.update_or_create(
                    sync=sync,
                    order_id=order.get('id'),
                    defaults={
                        'date': arrow.get(order.get('date_created')).datetime,
                        'order_name': order.get('number'),
                        'amount': order.get('total'),
                        'items': json.dumps([f'{i.get("quantity", 1)} x {i.get("name")}' for i in order.get('line_items', [])]),
                    }
                )

        # Lesser results than limit means we reached the end
        if len(orders) < limit:
            break
        page += 1
    sync.save()  # Update last sync


@celery_app.task(bind=True, base=CaptureFailure)
def sync_commercehq_store_profits(self, sync_id, store_id):
    sync = models.ProfitSync.objects.get(pk=sync_id)
    store = CommerceHQStore.objects.get(pk=store_id)

    chq_api_url = store.get_api_url('orders')
    r = store.request.get(chq_api_url)
    r.raise_for_status()

    orders = r.json()

    for order in orders.get('items', []):
        models.ProfitOrder.objects.update_or_create(
            sync=sync,
            order_id=order.get('id'),
            defaults={
                'date': arrow.get(order['order_date']).datetime,
                'order_name': order.get('display_number'),
                'amount': order.get('total'),
                'items': json.dumps([f'{i["status"].get("quantity", 1)} x {i["data"].get("title")}' for i in order.get('items', [])]),
            }
        )

    sync.save()  # Update last sync
