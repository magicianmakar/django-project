from django.core.cache import cache

import re
import arrow
import requests

from unidecode import unidecode
import simplejson as json

from shopify_orders.models import ShopifySyncStatus, ShopifyOrder, ShopifyOrderLine
from shopified_core.utils import OrderErrors
from shopified_core.shipping_helper import country_from_code


def safeInt(v, default=0):
    try:
        return int(v)
    except:
        return default


def str_max(text, max_len):
    if not text:
        return ''
    else:
        return text[:max_len]


def get_customer_name(customer):
    return u'{} {}'.format(
        customer.get('first_name', ''),
        customer.get('last_name', '')).strip()


def ensure_title(text):
    """ Ensure the given string start with an upper case letter """

    try:
        if text.encode().strip():
            is_lower = all([c.islower() or not c.isalpha() for c in text])
            if is_lower:
                return text.title()
    except:
        pass

    return text


def get_datetime(isodate, default=None):
    return arrow.get(isodate).datetime if isodate else default


def sort_orders(orders, page):
    orders_map = {}
    resorted = []

    for i in orders:
        orders_map[i['id']] = i

    for i in page:
        order = orders_map.get(i.order_id)
        if order:
            order['db_updated_at'] = arrow.get(i.updated_at).timestamp
            resorted.append(order)

    return resorted


def update_shopify_order(store, data, sync_check=True):
    if sync_check:
        try:
            sync_status = ShopifySyncStatus.objects.get(store=store)

            if sync_status.sync_status == 1:
                sync_status.add_pending_order(data['id'])
                return

            elif sync_status.sync_status not in [2, 5, 6]:
                # Retrn if not Completed, Disabled or in Reset
                return

        except ShopifySyncStatus.DoesNotExist:
            return

    address = data.get('shipping_address', data.get('customer', {}).get('default_address', {}))
    customer = data.get('customer', address)

    order, created = ShopifyOrder.objects.update_or_create(
        order_id=data['id'],
        store=store,
        defaults={
            'user': store.user,
            'order_number': data['number'],
            'customer_id': customer.get('id', 0),
            'customer_name': str_max(get_customer_name(customer), 255),
            'customer_email': str_max(customer.get('email'), 255),
            'financial_status': data['financial_status'],
            'fulfillment_status': data['fulfillment_status'],
            'total_price': data['total_price'],
            'tags': data['tags'],
            'city': str_max(address.get('city'), 63),
            'zip_code': str_max(address.get('zip'), 31),
            'country_code': str_max(address.get('country_code'), 31),
            'items_count': len(data.get('line_items', [])),
            'created_at': get_datetime(data['created_at']),
            'updated_at': get_datetime(data['updated_at']),
            'closed_at': get_datetime(data['closed_at']),
            'cancelled_at': get_datetime(data['cancelled_at']),
        }
    )

    connected_items = 0
    need_fulfillment = len(data.get('line_items', []))

    for line in data.get('line_items', []):
        cache_key = 'export_product_{}_{}'.format(store.id, line['product_id'])
        product = cache.get(cache_key)
        if product is None:
            product = store.shopifyproduct_set.filter(shopify_id=safeInt(line['product_id'])).first()
            cache.set(cache_key, product.id if product else 0, timeout=300)
        else:
            product = store.shopifyproduct_set.get(id=product) if product != 0 else None

        track = store.shopifyordertrack_set.filter(order_id=data['id'], line_id=line['id']).first()

        if product:
            connected_items += 1

        if track or line['fulfillment_status'] == 'fulfilled' or (product and product.is_excluded):
            need_fulfillment -= 1

        ShopifyOrderLine.objects.update_or_create(
            order=order,
            line_id=line['id'],
            defaults={
                'shopify_product': safeInt(line['product_id']),
                'title': line['title'],
                'price': line['price'],
                'quantity': line['quantity'],
                'variant_id': safeInt(line['variant_id']),
                'variant_title': line['variant_title'],
                'fulfillment_status': line['fulfillment_status'],
                'product': product,
                'track': track
            })

    order.need_fulfillment = need_fulfillment
    order.connected_items = connected_items
    order.save()


def update_line_export(store, shopify_id):
    """
    Update ShopifyOrderLine.product when a supplier is added or changed
    :param shopify_id: Shopify Product ID
    """

    product = store.shopifyproduct_set.filter(shopify_id=shopify_id).first()
    for order in ShopifyOrder.objects.filter(store=store, shopifyorderline__shopify_product=shopify_id).distinct():
        connected_items = 0
        for line in order.shopifyorderline_set.all():
            if line.shopify_product == safeInt(shopify_id):
                line.product = product
                line.save()

                if product:
                    connected_items += 1

            elif line.product_id:
                connected_items += 1

        if order.connected_items != connected_items:
            ShopifyOrder.objects.filter(id=order.id).update(connected_items=connected_items)


def delete_shopify_order(store, data):
    ShopifyOrder.objects.filter(store=store, order_id=data['id']).delete()


def is_store_synced(store, sync_type='orders'):
    ''' Return True if store orders have been synced '''
    try:
        sync_status = ShopifySyncStatus.objects.get(store=store)
        return sync_status.sync_status in [2, 5, 6]
    except ShopifySyncStatus.DoesNotExist:
        return False


def is_store_sync_enabled(store, sync_type='orders'):
    ''' Return True if store orders are in sync and not disabled '''

    try:
        sync_status = ShopifySyncStatus.objects.get(store=store)
        return sync_status.sync_status in [2, 6]
    except ShopifySyncStatus.DoesNotExist:
        return False


def support_product_filter(store, sync_type='orders'):
    ''' Return True if store support Filtered Products feature '''

    try:
        sync_status = ShopifySyncStatus.objects.get(store=store)
        return sync_status.revision > 1
    except ShopifySyncStatus.DoesNotExist:
        return False


def disable_store_sync(store):
    try:
        sync = ShopifySyncStatus.objects.get(store=store)

        # Disable only if import is Completed
        if sync.sync_status == 2 and sync.sync_status != 6:
            sync.sync_status = 5
            sync.save()

    except:
        pass


def enable_store_sync(store):
    try:
        sync = ShopifySyncStatus.objects.get(store=store)

        if sync.sync_status == 5:
            sync.sync_status = 2
            sync.save()

    except:
        pass


def change_store_sync(store):
    try:
        sync = ShopifySyncStatus.objects.get(store=store)

        if sync.sync_status == 5:
            sync.sync_status = 2
            sync.save()

    except:
        pass


def order_id_from_name(store, order_name, default=None):
    ''' Get Order ID from Order Name '''

    orders = ShopifyOrder.objects.filter(store=store)

    order_rx = store.user.get_config('order_number', {}).get(str(store.id), '[0-9]+')
    order_number = re.findall(order_rx, order_name)
    if not order_number:
        return default

    order_number = order_number[0]
    if len(order_number) > 7:
        # Order name should contain less than 7 digits
        return default

    params = {
        'status': 'any',
        'fulfillment_status': 'any',
        'financial_status': 'any',
        'fields': 'id',
        'name': order_name.strip()
    }

    rep = requests.get(
        url=store.get_link('/admin/orders.json', api=True),
        params=params
    )

    if rep.ok:
        orders = rep.json()['orders']

        if len(orders):
            return orders.pop()['id']

    return default


def order_ids_from_customer_id(store, customer_id):
    ''' Get Order IDs from Customer ID '''

    params = {
        'status': 'any',
        'fulfillment_status': 'any',
        'financial_status': 'any',
        'customer_id': customer_id
    }

    rep = requests.get(
        url=store.get_link('/admin/orders.json', api=True),
        params=params
    )

    if rep.ok:
        return [i['id'] for i in rep.json()['orders']]

    return []


class OrderErrorsCheck:
    ignored = 0
    errors = 0
    stdout = None

    def __init__(self, stdout=None):
        self.stdout = stdout

    def check(self, track, commit):
        try:
            track_data = json.loads(track.data)
            contact_name = track_data['aliexpress']['order_details']['customer']['contact_name']
        except:
            self.ignored += 1
            return

        parts = [i.strip() for i in track_data['aliexpress']['order_details']['customer']['country'].split(',')]
        city = parts[0]
        country = parts[len(parts) - 1]

        order = ShopifyOrder.objects.filter(store=track.store, order_id=track.order_id).first()
        if not order:
            self.ignored += 1
            return

        found_errors = 0
        erros_desc = []
        if order.customer_name and not self.compare_name(order.customer_name, contact_name):
            found_errors |= OrderErrors.NAME
            erros_desc.append(u'Customer Error: ' + order.customer_name + u' <> ' + contact_name)
            track.add_error(u"Customer is '{}' should be '{}'".format(contact_name, order.customer_name))

        if order.city and not self.compare_city(order.city, city):
            found_errors |= OrderErrors.CITY
            erros_desc.append(u'City Error: ' + order.city + u' <> ' + city)
            track.add_error(u"City is '{}' should be '{}'".format(city, order.city))

        shopiyf_country = country_from_code(order.country_code)
        if shopiyf_country and not self.compare_country(shopiyf_country, country):
            found_errors |= OrderErrors.COUNTRY
            erros_desc.append(u'Country Error: ' + shopiyf_country + u' <> ' + country)
            track.add_error(u"Country is '{}' should be '{}'".format(country, shopiyf_country))

        if found_errors:
            self.errors += 1

            self.write(
                track.store.title,
                u'#{}'.format(order.order_number + 1000),
                track.source_id,
                track.source_status,
                arrow.get(order.created_at).humanize(),
                order.total_price,
                u'\n\t' + u'\n\t'.join(erros_desc)
            )

        if commit:
            track.errors = found_errors if found_errors > 0 else -1
            track.save()

    def compare_name(self, first, second):
        first = self.clean_name(first)
        second = self.clean_name(second)

        return ensure_title(unidecode(first)).lower() in ensure_title(unidecode(second)).lower()

    def compare_city(self, first, second):
        first = self.clean_name(first)
        second = self.clean_name(second)

        match = unidecode(first).lower() == unidecode(second).lower()

        if not match:
            if ',' in first:
                for i in first.split(','):
                    if unidecode(i).strip().lower() == unidecode(second).lower():
                        return True

        return match

    def compare_country(self, first, second):
        if second == 'Puerto Rico':
            second = u'United States'

        first = self.clean_name(first)
        second = self.clean_name(second)

        return first.lower() == second.lower()

    def clean_name(self, name):
        name = re.sub(' +', ' ', name)
        name = re.sub(r'\bNone\b', '', name)

        return name.strip('.,-').strip()

    def write(self, *args):
        if self.stdout:
            self.stdout.write(u' | '.join([unicode(i) for i in args]))
