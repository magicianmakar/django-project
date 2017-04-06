from __future__ import absolute_import


from django.contrib.auth.models import User
from django.core.cache import cache

from raven.contrib.django.raven_compat.models import client as raven_client

from app.celery import celery_app, CaptureFailure

from leadgalaxy.models import ShopifyStore
from order_imports.api import ShopifyOrderImportAPI


@celery_app.task(bind=True, base=CaptureFailure)
def import_orders(self, store_id, parsed_orders, file_index=0):

    store = ShopifyStore.objects.get(id=store_id)
    api = ShopifyOrderImportAPI(store=store)

    try:
        data = api.find_orders(parsed_orders)

        cache.set('order_import_{}_{}'.format(file_index, store.pusher_channel()),
                  data.values(),
                  timeout=3600)

        store.pusher_trigger('order-import', {
            'success': True,
            'finished': True,
            'store_id': store_id,
            'file_index': file_index,
        })
    except Exception:
        raven_client.captureException()

        store.pusher_trigger('order-import', {
            'success': False,
            'finished': True,
            'store_id': store_id,
            'file_index': file_index
        })


@celery_app.task(bind=True, base=CaptureFailure)
def approve_imported_orders(self, user_id, data, pusher_store_id):
    from order_imports.api import ShopifyOrderImportAPI
    user = User.objects.get(pk=user_id)
    stores = user.profile.get_shopify_stores()
    pusher_store = stores.get(pk=pusher_store_id)

    try:
        for store_id, items in data.items():
            store = stores.get(pk=store_id)
            api = ShopifyOrderImportAPI(store=store)
            api.send_tracking_number(items)

        pusher_store.pusher_trigger('order-import-approve', {
            'success': True
        })
    except Exception:
        raven_client.captureException()

        pusher_store.pusher_trigger('order-import-approve', {
            'success': False
        })
