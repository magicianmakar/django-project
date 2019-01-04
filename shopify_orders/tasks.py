from __future__ import absolute_import

import requests

from django.conf import settings

from app.celery import celery_app, CaptureFailure

from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.models import ShopifyStore, ShopifyProduct, ShopifyOrderTrack
from shopify_orders.utils import OrderErrorsCheck, update_elasticsearch_shopify_order
from shopify_orders.models import ShopifyOrder


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def fulfill_shopify_order_line(self, store_id, order, customer_address, line_id=None):
    """ Try to Auto fulfill a Shopify Order if an item within this product support it

    This function look at each item in the order and try to detect lines that need to be
    auto fulfilled

    Args:
        store_id: Shopify Store ID
        order: Shopify Order Data (recieved from order create/update webhook)
        customer_address: address from shopify_customer_address
        line_id: (optional) Fulfil only this line ID
    """

    store = ShopifyStore.objects.get(id=store_id)

    order_tracks = {}
    for i in ShopifyOrderTrack.objects.filter(store=store, order_id=order['id']).defer('data'):
        order_tracks['{}-{}'.format(i.order_id, i.line_id)] = i

    have_aliexpress = False

    for el in order['line_items']:
        if line_id and int(line_id) != el['id']:
            continue

        variant_id = el['variant_id']
        if not el['product_id']:
            if variant_id:
                product = ShopifyProduct.objects.filter(store=store, title=el['title'], shopify_id__gt=0).first()
            else:
                product = None
        else:
            product = ShopifyProduct.objects.filter(store=store, shopify_id=el['product_id']).first()

        shopify_order = order_tracks.get('{}-{}'.format(order['id'], el['id']))

        if not product or shopify_order or el['fulfillment_status'] == 'fulfilled' or (product and product.is_excluded):
            continue

        variant_id = product.get_real_variant_id(variant_id)
        supplier = product.get_suppier_for_variant(variant_id)
        if not product.have_supplier() or not supplier:
            continue

        elif supplier.is_aliexpress:
            if line_id:
                return fulfill_aliexpress_order(store, order['id'], line_id)
            else:
                have_aliexpress = True

    if have_aliexpress:
        return fulfill_aliexpress_order(store, order)
    else:
        return False


def fulfill_aliexpress_order(store, order_id, line_id=None):
    if not settings.FULFILLBOX_API_URL:
        return 'Service API is not set'

    aliexpress_email = store.user.get_config('ali_email')
    if not aliexpress_email:
        return 'Aliexpress Account is not set'

    url = settings.FULFILLBOX_API_URL + '/api/aliexpress/order'
    rep = requests.put(
        url=url,
        json={
            'shop': str(store.shop),
            'order': str(order_id),
            'line_id': str(line_id if line_id else ''),
            'user': str(store.user.id),
            'store': {
                'id': str(store.id),
                'type': 'shopify',
                'title': store.title,
            },
            'token': store.user.get_access_token(),
            'aliexpress': {
                'email': aliexpress_email,
            }
        })

    try:
        rep.raise_for_status()
    except:
        raven_client.captureException()

    return rep.ok


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def check_track_errors(self, track_id):
    try:
        track = ShopifyOrderTrack.objects.get(id=track_id)
    except ShopifyOrderTrack.DoesNotExist:
        return

    orders_check = OrderErrorsCheck()
    orders_check.check(track, commit=True)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def index_shopify_order(self, order_pk):
    """
    Re-index the passed order

    Args:
        order_pk (int): ShopifyOrder primary key id
    """

    try:
        order = ShopifyOrder.objects.get(id=order_pk)
        update_elasticsearch_shopify_order(order)

    except ShopifyOrderTrack.DoesNotExist:
        pass

    except:
        raven_client.captureException()
