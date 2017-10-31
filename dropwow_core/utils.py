import requests

from django.conf import settings
from django.utils import timezone

from requests.auth import HTTPBasicAuth
from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.models import ShopifyOrderTrack
from leadgalaxy.utils import safeInt, get_shopify_order, get_shopify_order_line
from shopify_orders.utils import get_datetime


def get_dropwow_products(page, post_per_page, title, category_id, min_price, max_price, brand, vendor, order_by):
    feed = requests.get(
        url='{}/dropwow-products/'.format(settings.DROPWOW_API_HOSTNAME),
        params={
            'page': page,
            'page_size': post_per_page,
            'title': title,
            'category_id': category_id,
            'min_price': min_price,
            'max_price': max_price,
            'brand': brand,
            'vendor': vendor,
            'order_by': order_by,
        },
        auth=HTTPBasicAuth(settings.DROPWOW_API_USERNAME, settings.DROPWOW_API_PASSWORD)
    )

    feed.raise_for_status()

    return feed.json()


def get_dropwow_featured_products(count):
    feed = requests.get(
        url='{}/dropwow-products/random'.format(settings.DROPWOW_API_HOSTNAME),
        params={'count': count},
        auth=HTTPBasicAuth(settings.DROPWOW_API_USERNAME, settings.DROPWOW_API_PASSWORD)
    )

    feed.raise_for_status()

    return feed.json()


def get_dropwow_product(product_id):
    feed = requests.get(
        url='{}/dropwow-products/{}'.format(settings.DROPWOW_API_HOSTNAME, product_id),
        auth=HTTPBasicAuth(settings.DROPWOW_API_USERNAME, settings.DROPWOW_API_PASSWORD)
    )

    feed.raise_for_status()

    return feed.json()


def get_dropwow_product_options(product_id):
    product = get_dropwow_product(product_id)
    ret = []
    for option_id, option in product.get('options', {}).iteritems():
        item = {'title': option.get('option_name', '')}
        values = []
        for variant in option.get('variants', []):
            values.append({
                'title': variant.get('variant_name', ''),
                'image': variant.get('image_path', '')}
            )
        item['values'] = values
        ret.append(item)
    return ret


def get_dropwow_product_combination(product_id, shopify_options):
    product = get_dropwow_product(product_id)
    product_options = {}
    for shopify_option in shopify_options:
        variant_name = shopify_option.get('title')
        for option_id, option in product.get('options', {}).iteritems():
            for variant in option.get('variants', {}):
                if variant.get('variant_name', '') == variant_name:
                    product_options[option_id] = variant.get('variant_id', '')
    return product_options


def fulfill_dropwow_order(order_status):
    store = order_status.store
    dropwow_account = store.user.dropwow_account
    supplier = order_status.product.default_supplier
    order_data = get_shopify_order(store, order_status.shopify_order_id)
    line = get_shopify_order_line(store, order_status.shopify_order_id, order_status.shopify_line_id, shopify_data=order_data)
    dropwow_order_delay = safeInt(store.user.get_config('dropwow_order_delay'))
    if dropwow_order_delay:
        created_at = get_datetime(order_data['created_at'])
        fulfill_until = timezone.now() - timezone.timedelta(hours=dropwow_order_delay)
        if created_at > fulfill_until:
            order_status.pending = True
            order_status.save()
            return False
    try:
        rep = fulfill_dropwow_products(dropwow_account, order_status, supplier, line['variant_id'], line['quantity'])

        source_id = rep.get('order_id')
        if not source_id:
            raven_client.captureMessage('Empty Dropwow Response', extra={
                'rep': rep.text
            })

            order_status.error_message = 'DropWow Api Error'
            order_status.save()

            return False

        source_status = rep.get('status')
        source_tracking = rep.get('tracking_number')

        order_status.order_id = source_id
        order_status.status = source_status
        order_status.tracking_number = source_tracking
        order_status.error_message = ''
        order_status.pending = False
        order_status.save()

        track, created = ShopifyOrderTrack.objects.update_or_create(
            store=store,
            order_id=order_status.shopify_order_id,
            line_id=order_status.shopify_line_id,
            defaults={
                'user': store.user,
                'source_id': source_id,
                'source_type': 'dropwow',
                'source_status': source_status,
                'source_tracking': source_tracking,
                'created_at': timezone.now(),
                'updated_at': timezone.now(),
                'status_updated_at': timezone.now()
            }
        )

        store.pusher_trigger('order-source-id-add', {
            'track': track.id,
            'order_id': track.order_id,
            'line_id': track.line_id,
            'source_id': track.source_id,
        })

        return True

        # TODO: Add Orde Note Update
        # TODO: update need_fulfillment
        # order = ShopifyOrder.objects.get(store=store, order_id=order['id'])
        # need_fulfillment = order.need_fulfillment

        # for line in order.shopifyorderline_set.all():
        #     if line.line_id == line_id:
        #         line.track = track
        #         line.save()

        #         need_fulfillment -= 1
        # ShopifyOrder.objects.filter(id=order.id).update(need_fulfillment=need_fulfillment)
    except:
        raven_client.captureException()

        order_status.error_message = 'Dropwow API Error'
        order_status.save()

    return False


def fulfill_dropwow_products(dropwow_account, order_status, supplier, variant_id, quantity):
    data = {
        'products': {},
        'user_data': order_status.get_address()
    }
    if supplier.get_source_id() == 2525:
        # This is a temporary fix to order this product which options and is not avaialble in current products feed
        product_options = {
            "2533": "11699",
            "2534": "11700"
        }
    else:
        variant_mapping = order_status.product.get_variant_mapping(supplier=supplier)
        options = variant_mapping.get(str(variant_id), [])  # [{'title': option1_value}, {'title': option2_value}]
        # dropwow product options {"option_id": variant_id, "option_id": variant_id}
        product_options = get_dropwow_product_combination(supplier.get_source_id(), options)
    data['products'][supplier.get_source_id()] = {
        'amount': quantity,
        'product_options': product_options
    }
    r = requests.post(
        url='http://market.dropwow.com/api/order',
        json=data,
        auth=HTTPBasicAuth(dropwow_account.email, dropwow_account.api_key)
    )

    try:
        r.raise_for_status()
    except:
        raven_client.captureException(extra={'response': r.text})
        raise

    return r.json()


def get_dropwow_order(dropwow_account_email, dropwow_account_api_key, order_id):
    r = requests.get(
        url='http://market.dropwow.com/api/order/{}'.format(order_id),
        auth=HTTPBasicAuth(dropwow_account_email, dropwow_account_api_key)
    )

    try:
        r.raise_for_status()
    except:
        raven_client.captureException(extra={'response': r.text})
        raise

    return r.json()


def get_dropwow_categories():
    r = requests.get(
        url='{}/dropwow-categories/'.format(settings.DROPWOW_API_HOSTNAME),
        auth=HTTPBasicAuth(settings.DROPWOW_API_USERNAME, settings.DROPWOW_API_PASSWORD)
    )

    try:
        r.raise_for_status()
    except:
        raven_client.captureException(extra={'response': r.text})
        raise

    return r.json()
