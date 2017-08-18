from __future__ import absolute_import

import json

from app.celery import celery_app, CaptureFailure

from dropwow_core.utils import fulfill_dropwow_order
from leadgalaxy.models import ShopifyStore, ShopifyProduct, ShopifyOrderTrack
from dropwow_core.models import DropwowOrderStatus


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def fulfill_shopify_order_line(self, store_id, order, customer_address):
    """ Try to Auto fulfill a Shopify Order if an item within this product support it

    This function look at each item in the order and try to detect lines that need to be
    auto fulfilled (Currently using Dropwow)

    Args:
        store_id: Shopify Store ID
        order: Shopify Order Data (recieved from order create/update webhook)
        customer_address: address from shopify_customer_address
    """

    store = ShopifyStore.objects.get(id=store_id)

    order_tracks = {}
    for i in ShopifyOrderTrack.objects.filter(store=store, order_id=order['id']).defer('data'):
        order_tracks['{}-{}'.format(i.order_id, i.line_id)] = i

    for el in order['line_items']:
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

        if not product.have_supplier() or not product.default_supplier.is_dropwow:
            continue

        supplier = product.default_supplier

        order_status, created = DropwowOrderStatus.objects.update_or_create(
            store=store,
            shopify_order_id=order['id'],
            shopify_line_id=el['id'],
            defaults={
                'product': product,
                'customer_address': json.dumps(customer_address)
            }
        )

        fulfill_dropwow_order(store, order_status, order, el, supplier)
