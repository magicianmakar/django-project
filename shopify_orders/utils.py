from django.core.cache import cache
from django.conf import settings

import re
import arrow
import requests

from unidecode import unidecode
import simplejson as json

from elasticsearch import Elasticsearch

from shopify_orders.models import ShopifySyncStatus, ShopifyOrder, ShopifyOrderLine
from shopified_core.utils import OrderErrors, delete_model_from_db
from shopified_core.shipping_helper import country_from_code

from zapier_core.utils import send_shopify_order_event


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


def sort_es_orders(orders, hits, db_orders):
    shopify_orders_map = {}
    db_orders_map = {}
    resorted = []

    for i in orders:
        shopify_orders_map[i['id']] = i

    for order in db_orders:
        db_orders_map[order.order_id] = order

    for i in hits:
        order = shopify_orders_map.get(i['_source']['order_id'])
        db_order = db_orders_map.get(i['_source']['order_id'])

        if order:
            order['es_updated_at'] = arrow.get(i['_source']['updated_at']).timestamp
            order['db_updated_at'] = arrow.get(db_order.updated_at).timestamp

            resorted.append(order)

    return resorted


def get_elastic(verify_certs=False):
    if any(settings.ELASTICSEARCH_API):
        if any(settings.ELASTICSEARCH_AUTH):
            return Elasticsearch(settings.ELASTICSEARCH_API, http_auth=settings.ELASTICSEARCH_AUTH, verify_certs=verify_certs)
        else:
            return Elasticsearch(settings.ELASTICSEARCH_API, verify_certs=verify_certs)

    return None


def update_elasticsearch_shopify_order(order):
    es = get_elastic()

    if not es:
        return

    es.index(
        index="shopify-order",
        doc_type="order",
        id=order.id,
        body=dict(
            store=order.store_id,
            user=order.user_id,
            order_id=order.order_id,
            order_number=order.order_number,
            customer_id=order.customer_id,
            customer_name=order.customer_name,
            customer_email=order.customer_email,
            financial_status=order.financial_status,
            fulfillment_status=order.fulfillment_status,
            total_price=order.total_price,
            tags=order.tags,
            city=order.city,
            zip_code=order.zip_code,
            country_code=order.country_code,
            items_count=order.items_count,
            need_fulfillment=order.need_fulfillment,
            connected_items=order.connected_items,
            created_at=order.created_at,
            updated_at=order.updated_at,
            closed_at=order.closed_at,
            cancelled_at=order.cancelled_at,
            product_ids=[l.product_id for l in order.shopifyorderline_set.all()]
        )
    )


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

    order = ShopifyOrder.objects.filter(order_id=data['id'], store=store).first()
    if order is not None:
        is_cancelled = order.is_cancelled
        financial_status = order.financial_status
        fulfillment_status = order.fulfillment_status

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
    if created:
        send_shopify_order_event('shopify_order_created', store, data)
    else:
        if not is_cancelled and order.is_cancelled:
            send_shopify_order_event('shopify_order_cancelled', store, data)
        if financial_status != order.financial_status or fulfillment_status != order.fulfillment_status:
            send_shopify_order_event('shopify_order_status_changed', store, data)

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

    if sync_status.elastic:
        update_elasticsearch_shopify_order(order)


def update_line_export(store, shopify_id):
    """
    Update ShopifyOrderLine.product when a supplier is added or changed
    :param shopify_id: Shopify Product ID
    """

    try:
        sync_status = ShopifySyncStatus.objects.get(store=store)
    except ShopifySyncStatus.DoesNotExist:
        sync_status = None

    update_elastic = is_store_synced(store) and sync_status.elastic

    product = store.shopifyproduct_set.filter(shopify_id=shopify_id).first()
    seen_orders = []
    for order in ShopifyOrder.objects.filter(store=store, shopifyorderline__shopify_product=shopify_id):  # TODO: Index shopify_product column
        if order.id not in seen_orders:
            seen_orders.append(order.id)
        else:
            continue

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

            if update_elastic:
                update_elasticsearch_shopify_order(order)


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


def is_store_indexed(store, sync_type='orders'):
    ''' Return True if store orders are indexed on elasticsearch '''
    try:
        sync_status = ShopifySyncStatus.objects.get(store=store)
        return sync_status.sync_status in [2, 6] and sync_status.elastic
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

    order_name = order_name.strip() if order_name else ''
    if not order_name:
        return default

    rx = re.compile(r'[^a-zA-Z0-9_-]')
    params = {
        'status': 'any',
        'fulfillment_status': 'any',
        'financial_status': 'any',
        'fields': 'id,name',
        'name': order_name.strip()
    }

    rep = requests.get(
        url=store.get_link('/admin/orders.json', api=True),
        params=params
    )

    if rep.ok:
        orders = rep.json()['orders']

        for i in orders:
            if rx.sub('', i['name']) == rx.sub('', order_name):
                return i['id']

    params['ids'] = order_name
    del params['name']

    rep = requests.get(
        url=store.get_link('/admin/orders.json', api=True),
        params=params
    )

    if rep.ok:
        orders = rep.json()['orders']

        for i in orders:
            if str(i['id']) == rx.sub('', order_name):
                return i['id']

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


def store_saved_orders(store, es=None):
    """ Get total saved orders in the database if es is not set, otherwise return total orders in Elastic index

    Args:
        store (ShopifyStore): Store to find orders count
        es (Elasticsearch, optional): Elastic index
    """

    if not es:
        return ShopifyOrder.objects.filter(store=store).count()
    else:
        body = {
            'query': {
                'bool': {
                    'must': [
                        {'term': {'store': store.id}},
                    ],
                },
            },
        }

        matchs = es.search(index='shopify-order', doc_type='order', body=body)
        return matchs['hits']['total']


def find_missing_order_ids(store, order_ids, es=None):
    """ Return the Order IDs that are in `order_ids` and not in database or ES saved orders

    Args:
        store (ShopifyStore): Store model
        order_ids (list): Shopify Order IDs list
        es (Elasticsearch, optional): is not set, search in the database, otherwise search in Elastic
    """

    missing_orders = []

    if not es:
        saved_order_ids = list(ShopifyOrder.objects.filter(store=store, order_id__in=order_ids)
                                                   .values_list('order_id', flat=True))
    else:
        body = {
            'query': {
                'bool': {
                    'must': [
                        {'term': {'store': store.id}},
                        {'bool': {'should': [{'term': {'order_id': i}} for i in order_ids]}}
                    ],
                },
            },
            'sort': [{
                'order_id': 'asc'
            }],
            'size': 250,
            'from': 0
        }

        matchs = es.search(index='shopify-order', doc_type='order', body=body, filter_path='hits.hits._source.order_id')
        saved_order_ids = [int(i['_source']['order_id']) for i in matchs['hits']['hits']]

    for i in order_ids:
        if i not in saved_order_ids:
            missing_orders.append(i)

    return missing_orders


def delete_store_orders(store, db=True, es=True):
    deleted = []

    if db:
        count = delete_model_from_db(ShopifyOrder, match={'store': store}, steps=2000)
        deleted.append(count)

    if es:
        es = get_elastic()
        if es:
            body = {
                'query': {
                    'bool': {
                        'must': [
                            {'term': {'store': store.id}},
                        ],
                    },
                },
            }

            r = es.delete_by_query(index='shopify-order', doc_type='order', body=body)
            deleted.append(r['total'])

            ShopifySyncStatus.objects.filter(store=store, elastic=True).update(elastic=False)

    return deleted


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
        if contact_name and not self.compare_name(order.customer_name, contact_name):
            found_errors |= OrderErrors.NAME
            erros_desc.append(u'Customer Error: ' + order.customer_name + u' <> ' + contact_name)
            track.add_error(u"Customer is '{}' should be '{}'".format(contact_name, order.customer_name))

        if city and not self.compare_city(order.city, city):
            found_errors |= OrderErrors.CITY
            erros_desc.append(u'City Error: ' + order.city + u' <> ' + city)
            track.add_error(u"City is '{}' should be '{}'".format(city, order.city))

        shopiyf_country = country_from_code(order.country_code)
        if country and not self.compare_country(shopiyf_country, country):
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
            if found_errors > 0:
                track.errors = found_errors
            else:
                if track.errors > 0:
                    # Clear previous errors
                    track.clear_errors(commit=False)

                track.errors = -1

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
