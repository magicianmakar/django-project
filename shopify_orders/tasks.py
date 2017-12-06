from __future__ import absolute_import

import json

from app.celery import celery_app, CaptureFailure

from raven.contrib.django.raven_compat.models import client as raven_client

from dropwow_core.utils import fulfill_dropwow_order
from leadgalaxy.models import ShopifyStore, ShopifyProduct, ShopifyOrderTrack
from dropwow_core.models import DropwowOrderStatus
from shopify_orders.utils import OrderErrorsCheck, update_elasticsearch_shopify_order
from shopify_orders.models import ShopifyOrder


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def fulfill_shopify_order_line(self, store_id, order, customer_address, line_id=None):
    """ Try to Auto fulfill a Shopify Order if an item within this product support it

    This function look at each item in the order and try to detect lines that need to be
    auto fulfilled (Currently using Dropwow)

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
        if not product.have_supplier() or not supplier or not supplier.is_dropwow:
            continue

        order_status, created = DropwowOrderStatus.objects.update_or_create(
            store=store,
            shopify_order_id=order['id'],
            shopify_line_id=el['id'],
            defaults={
                'product': product,
                'customer_address': json.dumps(customer_address)
            }
        )

        fulfill_dropwow_order(order_status)


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
