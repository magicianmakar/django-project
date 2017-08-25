import json
from time import sleep

from django.contrib.auth.models import User

from raven.contrib.django.raven_compat.models import client as raven_client

from app.celery import celery_app, CaptureFailure

from shopified_core.utils import safeFloat
from shopify_orders.models import ShopifyOrder
from leadgalaxy.models import ShopifyOrderTrack

from .models import ShopifyProfit, ShopifyProfitImportedOrder


@celery_app.task(bind=True, base=CaptureFailure)
def fetch_facebook_insights(self, user_id, store_id, access_token):
    from .utils import get_facebook_ads

    user = User.objects.get(pk=user_id)
    store = user.profile.get_shopify_stores().filter(pk=store_id).first()
    try:
        get_facebook_ads(user, access_token)

        store.pusher_trigger('facebook-insights', {
            'success': True
        })
    except Exception as e:
        raven_client.captureException()

        store.pusher_trigger('facebook-insights', {
            'success': False,
            'error': str(e),
        })


@celery_app.task(bind=True, base=CaptureFailure)
def cache_shopify_profits(self, user_id, store_id, found_orders):
    sleep(5)  # Waiting for page to reload so cache doesn't finish first and no profits are sent
    user = User.objects.get(pk=user_id)
    store = user.profile.get_shopify_stores().filter(pk=store_id).first()
    try:
        # Get data from shopify orders
        orders = ShopifyOrder.objects.filter(pk__in=found_orders)
        tracks = ShopifyOrderTrack.objects.filter(store_id=store_id)

        result = {}
        for order in orders:
            date_key = order.created_at.date()

            fulfillment_cost = 0.0
            for track in tracks.filter(order_id=order.order_id):
                try:
                    data = json.loads(track.data)
                except:
                    continue

                if data.get('aliexpress') and data.get('aliexpress').get('order_details') and \
                        data.get('aliexpress').get('order_details').get('cost'):

                    fulfillment_cost += safeFloat(data['aliexpress']['order_details']['cost'].get('shipping'))

                    # Only add shipping cost once, because it store total shipping cost not just line cost
                    break

            if date_key in result:
                result[date_key]['revenue'] += order.total_price
                result[date_key]['fulfillment_cost'] += fulfillment_cost
                result[date_key]['order_ids'].append(order.order_id)
            else:
                result[date_key] = {
                    'revenue': order.total_price,
                    'fulfillment_cost': fulfillment_cost,
                    'order_ids': [order.order_ids]
                }

        for date, profit_data in result.items():
            profit, created = ShopifyProfit.objects.update_or_create(
                date=date,
                store_id=store_id,
                defaults={
                    'revenue': profit_data['revenue'],
                    'fulfillment_cost': profit_data['fulfillment_cost'],
                }
            )

            # Save imported order_ids
            imported_orders = []
            for order_id in profit_data['order_ids']:
                imported_orders.append(ShopifyProfitImportedOrder(profit=profit, order_id=order_id))

            ShopifyProfitImportedOrder.objects.bulk_create(imported_orders)

        store.pusher_trigger('profit-calculations', {
            'success': True
        })
    except:
        raven_client.captureException()

        store.pusher_trigger('profit-calculations', {
            'success': False
        })
