import json

from django.contrib.auth.models import User
from django.db.models import F, Value, CharField
from django.db.models.functions import Concat

from raven.contrib.django.raven_compat.models import client as raven_client

from app.celery import celery_app, CaptureFailure

from shopified_core.utils import safeFloat
from shopify_orders.models import ShopifyOrder
from leadgalaxy.models import ShopifyStore, ShopifyOrderTrack

from .models import (
    ShopifyProfit,
    ShopifyProfitImportedOrder,
    ShopifyProfitImportedOrderTrack,
)


@celery_app.task(bind=True, base=CaptureFailure)
def fetch_facebook_insights(self, user_id, store_id, access_token, account_ids, campaigns):
    from .utils import get_facebook_ads

    user = User.objects.get(pk=user_id)
    store = user.profile.get_shopify_stores().filter(pk=store_id).first()
    try:
        get_facebook_ads(user, store, access_token, account_ids, campaigns)

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
def cache_shopify_profits(self, store_id, found_order_ids, order_track_ids, imported_order_ids, order_source_ids):
    store = ShopifyStore.objects.get(pk=store_id)
    try:
        # Get data from order tracks
        found_order_tracks = {}
        sources = {}
        for order_track in ShopifyOrderTrack.objects.filter(pk__in=order_track_ids):
            try:
                data = json.loads(order_track.data)
            except:
                continue

            # Initialize dicts by order_id
            if order_track.order_id not in found_order_tracks:
                found_order_tracks[order_track.order_id] = []
                sources[order_track.order_id] = []

            if order_track.source_id not in sources[order_track.order_id]:
                found_order_tracks[order_track.order_id].append({'data': data, 'source_id': order_track.source_id})
                # Prevent importing sources more than once
                sources[order_track.order_id].append(order_track.source_id)

        # Merge data from shopify orders and order tracks
        orders = ShopifyOrder.objects.filter(store_id=store_id, order_id__in=found_order_ids)
        result = {}
        for order in orders:
            date_key = order.created_at.date()

            fulfillment_cost = 0.0
            order_tracks = []
            for track_data in found_order_tracks.get(order.order_id, []):
                cost_total = safeFloat(track_data['data']['aliexpress']['order_details']['cost'].get('total'))
                fulfillment_cost += cost_total
                order_tracks.append({'order_id': order.order_id, 'source_id': track_data['source_id'], 'amount': cost_total})

            if date_key not in result:
                result[date_key] = {
                    'revenue': 0.0,
                    'fulfillment_cost': 0.0,
                    'order_ids': [],
                    'order_tracks': []
                }

            if order.order_id not in imported_order_ids:
                result[date_key]['revenue'] += order.total_price
                result[date_key]['order_ids'].append(order.order_id)

            result[date_key]['fulfillment_cost'] += fulfillment_cost
            result[date_key]['order_tracks'] += order_tracks

        # Save gathered data
        for date, profit_data in result.items():
            profit, created = ShopifyProfit.objects.get_or_create(
                date=date,
                store_id=store_id,
                defaults={
                    'revenue': profit_data['revenue'],
                    'fulfillment_cost': profit_data['fulfillment_cost'],
                }
            )

            # If profit is already created, update values with recently found
            if not created:
                profit.revenue = F('revenue') + profit_data['revenue']
                profit.fulfillment_cost = F('fulfillment_cost') + profit_data['fulfillment_cost']
                profit.save()

            # Save imported order_ids
            imported_orders = []
            for order_id in profit_data['order_ids']:
                imported_orders.append(ShopifyProfitImportedOrder(profit=profit, order_id=order_id))

            ShopifyProfitImportedOrder.objects.bulk_create(imported_orders)

            # Save imported order_ids from ShopifyOrderTrack
            imported_order_tracks = []
            for order_track in profit_data['order_tracks']:
                imported_order_tracks.append(ShopifyProfitImportedOrderTrack(
                    profit=profit,
                    order_id=order_track['order_id'],
                    source_id=order_track['source_id'],
                    amount=order_track['amount']
                ))

            ShopifyProfitImportedOrderTrack.objects.bulk_create(imported_order_tracks)

        # Delete erased order track source ids previously imported
        found_order_source_ids = ShopifyOrderTrack.objects.filter(
            store_id=store_id
        ).annotate(
            order_source_id=Concat('order_id', Value('-'), 'source_id', output_field=CharField())
        ).filter(
            order_source_id__in=order_source_ids
        ).values_list('order_source_id', flat=True).order_by('order_source_id').distinct()
        delete_order_source_ids = [source for source in order_source_ids if source not in found_order_source_ids]

        delete_order_tracks = ShopifyProfitImportedOrderTrack.objects.filter(
            profit__store_id=store_id
        ).annotate(
            order_source_id=Concat('order_id', Value('-'), 'source_id', output_field=CharField())
        ).filter(
            order_source_id__in=delete_order_source_ids
        )

        for order_track in delete_order_tracks:
            order_track.profit.fulfillment_cost -= order_track.amount
            order_track.profit.save()

        delete_order_tracks.delete()

        store.pusher_trigger('profit-calculations', {'success': True})
    except:
        raven_client.captureException()

        store.pusher_trigger('profit-calculations', {'success': False})
