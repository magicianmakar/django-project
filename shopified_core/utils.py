import os
import re
import base64
import hashlib
import time
import hmac
import mimetypes
import ctypes
import simplejson as json
from functools import wraps
from copy import deepcopy
from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.core import serializers
from django.core.mail import send_mail
from django.core.cache import cache, caches
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.template import Context, Template
from django.template.defaultfilters import pluralize
from django.utils.crypto import get_random_string

import arrow
import bleach
import phonenumbers
from tld import get_tld


ALIEXPRESS_REJECTED_STATUS = {
    "buyer_pay_timeout": "Order Payment Timeout",
    "risk_reject_closed": "Rejected By Risk Control",
    "buyer_cancel_notpay_order": "Buyer Cancel or Doesn't Pay Order",
    "cancel_order_close_trade": "Cancel Order Close Trade",
    "seller_send_goods_timeout": "Seller Send Goods Timeout",
    "buyer_cancel_order_in_risk": "Buyer Cancel Order In Risk",
    "seller_accept_issue_no_goods_return": "Seller Accept Issue No Goods Return",
    "seller_response_issue_timeout": "Seller Response Issue Timeout",
}

ALIEXPRESS_SOURCE_STATUS = {}
ALIEXPRESS_SOURCE_STATUS.update({
    **ALIEXPRESS_REJECTED_STATUS,
    "buyer_accept_goods_timeout": "Buyer Accept Goods Timeout",
    "buyer_accept_goods": "Buyer Accept Goods",
})


class OrderErrors:
    NAME = 1
    CITY = 2
    COUNTRY = 4


def safe_int(v, default=0):
    try:
        return int(v)
    except:
        return default


def safe_float(v, default=0.0):
    try:
        return float(v)
    except:
        return default


def safe_str(v, default=''):
    """ Always return a str object """

    if isinstance(v, str):
        return v
    else:
        return default


def dict_val(data, name, default=None):
    """ Return dict value or default value if no key is found

    if name is a list, return the first value found in data
    """

    if type(name) is list:
        for i in name:
            if i in data:
                return data[i]

        return default
    else:
        return data.get(name, default)


def prefix_from_model(model):
    prefix = model._meta.app_label
    if prefix == 'leadgalaxy':
        return 'shopify'
    elif prefix == 'commercehq_core':
        return 'chq'
    elif prefix == 'woocommerce_core':
        return 'woo'
    elif prefix == 'groovekart_core':
        return 'gkart'
    elif prefix == 'gearbubble_core':
        return 'gear'
    else:
        return None


def list_chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]


def app_link(*args, **kwargs):
    """
    Get full link to a web app page

    Example:
        app_link('orders')
        app_link('orders/track') or app_link('orders', 'track')
        app_link('orders/track', query=1001)
    """

    path = '/'.join([str(i) for i in args]).lstrip('/') if args else ''

    if kwargs:
        for k, v in list(kwargs.items()):
            if type(v) is bool:
                kwargs[k] = str(v).lower()
            elif isinstance(v, str):
                kwargs[k] = v

        path = '{}?{}'.format(path, urlencode(kwargs))

    return '{}/{}'.format(settings.APP_URL, path.lstrip('/')).rstrip('/')


def remove_trailing_slash(t):
    t = safe_str(t, str(t))
    return t.strip('/')


def url_join(*args):
    url = [remove_trailing_slash(i) for i in args]
    return '/'.join(url).rstrip('/')


def hash_text(text):
    return hashlib.md5(text.encode()).hexdigest()


def hash_list(data, sep=''):
    return hash_text(sep.join([str(i) for i in data]))


def random_hash():
    token = get_random_string(32)
    return hashlib.md5(token.encode()).hexdigest()


def base64_encode(s):
    if type(s) is str:
        s = s.encode()

    return base64.encodebytes(s).decode().replace('\n', '').strip()


def base64_decode(s):
    if type(s) is str:
        s = s.encode()

    return base64.decodebytes(s).decode()


def encode_params(val):
    val = val or ''
    return 'b:{}'.format(base64_encode(val))


def decode_params(val):
    if val:
        if val.startswith('b:'):
            return base64_decode(val[2:])

        elif not safe_int(val):
            try:
                r = base64_decode(val)
                if '@' in r:
                    # Return the encoded value only if we have @ char in the decode string
                    # This will help us prevent decoding numbers (ex: 4624) as valid base64 encoded strings
                    return r
            except:
                pass

    return val


def all_possible_cases(arr, top=True):
    sep = '_'.join([str(i) for i in range(10)])

    if (len(arr) == 0):
        return []
    elif (len(arr) == 1):
        return arr[0]
    else:
        result = []
        allCasesOfRest = all_possible_cases(arr[1:], False)
        for c in allCasesOfRest:
            for i in arr[0]:
                result.append('{}{}{}'.format(i, sep, c))

        return [k.split(sep) for k in result] if top else result


def get_domain(url, full=False):
    if not url:
        return None

    if not url.startswith('http'):
        url = 'http://{}'.format(url)

    hostname = urlparse(url).hostname
    if hostname is None:
        return hostname

    if full:
        return hostname
    else:
        return get_tld(url, as_object=True).domain


def add_http_schema(url):
    if not url.startswith('http'):
        return 'http://{}'.format(url.lstrip(':/'))
    else:
        return url


def remove_link_query(link):
    if not link:
        return ''

    if not link.startswith('http'):
        link = 'http://{}'.format(re.sub('^([:/]*)', r'', link))

    return re.sub('([?#].*)$', r'', link)


def get_filename_from_url(url):
    return remove_link_query(url).split('/').pop()


def get_fileext_from_url(url, fallback=''):
    name = get_filename_from_url(url)
    if '.' in name:
        return name.split('.').pop()
    else:
        return fallback


def extension_hash_text(s):
    hashval = 0

    if not len(s):
        return hashval

    for i in range(len(s)):
        ch = ord(s[i])
        hashval = int(((hashval << 5) - hashval) + ch)
        hashval |= 0

    return ctypes.c_int(hashval & 0xFFFFFFFF).value


def hash_url_filename(s):
    url = remove_link_query(s)
    ext = get_fileext_from_url(s, fallback='jpg')

    if not re.match(r'(gif|jpe?g|png|ico|bmp)$', ext, re.I):
        ext = 'jpg'

    hashval = extension_hash_text(url)

    return '{}.{}'.format(ctypes.c_int(hashval & 0xFFFFFFFF).value, ext) if hashval else hashval


def get_mimetype(url, default=None):
    content_type = mimetypes.guess_type(remove_link_query(url))[0]
    return content_type if content_type else default


def send_email_from_template(tpl, subject, recipient, data, nl2br=False, from_email=None, is_async=False):
    template_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'emails', tpl)
    template = Template(open(template_file).read())

    ctx = Context(data)

    email_html = template.render(ctx)

    if nl2br and '<head' not in email_html and '<body' not in email_html:
        email_plain = email_html
        email_html = email_html.replace('\n', '<br />')
    else:
        email_plain = bleach.clean(email_html, tags=[], strip=True).strip().split('\n')
        email_plain = [l.strip() for l in email_plain]
        email_plain = '\n'.join(email_plain)

    if type(recipient) is not list:
        recipient = [recipient]

    if from_email is None:
        from_email = '"Dropified" <support@dropified.com>'

    kwargs = dict(subject=subject,
                  recipient_list=recipient,
                  from_email=from_email,
                  message=email_plain,
                  html_message=email_html)

    if is_async:
        from shopified_core.tasks import send_email_async
        send_email_async.apply_async(kwargs=kwargs, queue='priority_high')
    else:
        send_mail(**kwargs)

    return email_html


def login_attempts_exceeded(username):
    tries_key = 'login_attempts_{}'.format(hash_text(username.lower()))
    tries = cache.get(tries_key)
    if tries is None:
        tries = {'count': 1, 'username': username}
    else:
        tries['count'] = tries.get('count', 1) + 1

    cache.set(tries_key, tries, timeout=600)

    if tries['count'] != 1:
        if tries['count'] < 10:
            time.sleep(1)
            return False
        else:
            return True
    else:
        return False


def login_attempts_reset(username):
    tries_key = 'login_attempts_{}'.format(hash_text(username.lower()))
    cache.delete(tries_key)


def unlock_account_email(username):
    try:
        if '@' in username:
            user = User.objects.get(email__iexact=username, profile__shopify_app_store=False)
        else:
            user = User.objects.get(username__iexact=username)
    except:
        return False

    unlock_token = random_hash()
    if cache.get('unlock_email_{}'.format(hash_text(username.lower()))) is not None:
        # Email already sent
        return False

    cache.set('unlock_account_{}'.format(unlock_token), {
        'user': user.id,
        'username': username
    }, timeout=660)

    send_email_from_template(
        tpl='account_unlock_instructions.html',
        subject='Unlock instructions',
        recipient=user.email,
        data={
            'username': user.get_first_name(),
            'unlock_link': app_link(reverse('user_unlock', kwargs={'token': unlock_token}))
        }
    )

    cache.set('unlock_email_{}'.format(hash_text(username.lower())), True, timeout=660)

    return True


def aws_s3_context():
    aws_available = (settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY and settings.AWS_STORAGE_BUCKET_NAME)

    conditions = [
        ["starts-with", "$utf8", ""],
        # Change this path if you need, but adjust the javascript config
        ["starts-with", "$key", "uploads"],
        ["starts-with", "$name", ""],
        ["starts-with", "$Content-Type", "image/"],
        ["starts-with", "$filename", ""],
        {"bucket": settings.AWS_STORAGE_BUCKET_NAME},
        {"acl": "public-read"}
    ]

    policy = {
        # Valid for 3 hours. Change according to your needs
        "expiration": arrow.now().replace(hours=+3).format("YYYY-MM-DDTHH:mm:ss") + 'Z',
        "conditions": conditions
    }

    policy_str = json.dumps(policy)
    string_to_sign = base64_encode(policy_str)

    signature = base64_encode(hmac.new(settings.AWS_SECRET_ACCESS_KEY.encode(), string_to_sign.encode(), hashlib.sha1).digest())

    return {
        'aws_available': aws_available,
        'aws_policy': string_to_sign,
        'aws_signature': signature,
    }


def clean_query_id(qid):
    ids = re.findall('([0-9]+)', qid)
    if len(ids):
        return safe_int(ids[0], 0)
    else:
        return 0


def compare(a, b):
    return (a > b) - (a < b)


def version_compare(left, right):
    def normalize(v):
        return [int(x) for x in re.sub(r'(\.0+)*$', '', v).split(".")]

    return compare(normalize(left), normalize(right))


def order_data_cache_key(*args, prefix='order'):
    order_key = '_'.join([str(i) for i in args])

    if not order_key.count('order_'):
        prefix = prefix.strip('_')
        order_key = f'{prefix}_{order_key}'

    return order_key


def order_data_cache(*args, prefix='order'):
    order_key = order_data_cache_key(*args, prefix=prefix)

    if '*' in order_key:
        data = caches['orders'].get_many(caches['orders'].keys(order_key))
    else:
        data = caches['orders'].get(order_key)

    return data


def orders_update_limit(orders_count, check_freq=30, total_time=360, min_count=20):
    """
    Calculate Orders update check limit

    orders_count: Total number of orders
    check_freq: Extension check interval (minutes)
    total_time: Total time amount to verify all orders (minutes)
    min_count: Minimum orders check limit
    """

    limit = (orders_count * check_freq) / total_time

    return max(limit, min_count)


def order_phone_number(request, user, phone_number, customer_country):
    if not phone_number or user.get_config('order_default_phone') != 'customer':
        phone_number = user.get_config('order_phone_number')
        country = user.profile.country

        if phone_number and '2056577766' in re.sub('[^0-9]', '', phone_number) and user.models_user.username != 'chase':
            phone_number = '0000000000'
    else:
        country = customer_country

    if phone_number:
        if phone_number.startswith('+'):
            try:
                parsed = phonenumbers.parse(phone_number)
                return '+{}|{}'.format(parsed.country_code, parsed.national_number).split('|')
            except:
                pass

        phone_number = ''.join(re.findall('[0-9]+', phone_number))

    if not phone_number or re.match('^0+$', phone_number):
        return '+{}|{}'.format(max(phonenumbers.country_code_for_region(customer_country), 1), phone_number).split('|')

    try:
        parsed = phonenumbers.parse(phone_number, country)
        return '+{}|{}'.format(parsed.country_code, parsed.national_number).split('|')
    except:
        pass

    try:
        number = '+' + phone_number[2:] if phone_number.startswith('00') else phone_number
        parsed = phonenumbers.parse(number, country)
        return '+{}|{}'.format(parsed.country_code, parsed.national_number).split('|')
    except:
        pass

    return None, phone_number


def get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')

    if forwarded_for:
        ip = forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')

    return ip


def save_user_ip(request, user=None):
    if user is None:
        user = request.user

    ip = get_client_ip(request)
    user.profile.add_ip(ip)


def unique_username(username='user', fullname=None):

    if '@' in username:
        username = username.split('@')[0]

    if username.strip() and not User.objects.filter(username__iexact=username.strip()).exists():
        return username.lower().strip()

    n = 0

    if type(fullname) is list:
        fullname = ' '.join(fullname).strip()

    if fullname:
        fullname = re.sub(r'[^a-zA-Z0-9_ -]', '', fullname).strip()
        fullname = re.sub(r'[ ]+', '.', fullname)

        if len(fullname) > len(username):
            username = fullname

    if not username:
        username = 'user'

    username = username.lower().strip()
    if len(username) > 30:
        username = re.sub(r'[^a-zA-Z]', '', username).strip()

    new_username = username[:30]

    while User.objects.filter(username__iexact=new_username).exists():
        n += 1
        new_username = '{}{}'.format(username.strip()[:29], n)

    return new_username


def update_product_data_images(product, old_url, new_url):
    images = product.parsed.get('images')
    images = [new_url if url == old_url else url for url in images]
    hashed_new = hash_url_filename(new_url)
    hashed_old = hash_url_filename(old_url)

    variants_images = product.parsed.get('variants_images') or {}
    if hashed_old in variants_images:
        variants_images[hashed_new] = variants_images.pop(hashed_old)

    product.update_data({'images': images, 'variants_images': variants_images})
    product.save()

    return product


def delete_model_from_db(model, match, steps=5000):
    """ Delete rows from a table using `match` filter

    This method will delete rows without using a lot of memory, deleting many rows at once may take a lot of memory and could exceed the container
    allowed memory if filter match many rows (ex: ShopifyOrder.objects.filter(user=n).delete() won't work if the user have 100K or more orders)

    Args:
        model: Model instance (ex: ShopifyOrder)
        match(dict): Filter to match rows to delete
    """

    model_ids = list(model.objects.filter(**match).values_list('id', flat=True))
    model_count = len(model_ids)

    steps = 10000
    start = 0
    count = 0
    while start < model_count:
        order_ids = model_ids[start:start + steps]
        model.objects.filter(id__in=order_ids).delete()

        start += steps
        count += len(order_ids)

    return count


def execute_once_in(unique_ids, seconds):
    """
    This decorator wraps a normal function
    so that it can be executed only once in the next few seconds.

    Usage:

    @execute_once_in([user.id, store.id], 3600)
    def myfunction():
        pass

    If called multiple times, the above method will be executed only one
    time during the next hour following its first execution.
    """

    def decorator(func):
        def inner_decorator(*args, **kwargs):
            key = "%s.%s.%s" % (func.__module__, func.__name__, hash_list(unique_ids))
            key = key.replace(' ', '_')  # memcache doesn't like spaces

            # NB: there's no way to tell if
            # func() didn't execute or returned nothing
            if cache.get(key):
                return

            cache.set(key, True, seconds)
            return func(*args, **kwargs)

        return wraps(func)(inner_decorator)

    return decorator


def last_executed(unique_ids, timeout, save=True):
    key = '_last_executed_{}'.format(hash_list(unique_ids))
    key = key.replace(' ', '_')

    seen = cache.get(key)

    if not seen and save:
        cache.set(key, arrow.utcnow().timestamp, timeout=timeout)

    return seen


def http_exception_response(e, json=False, extra=True):
    try:
        if json:
            return e.response.json()
        elif extra:
            return {'response': e.response.text}
        else:
            return e.response.text
    except:
        if json:
            return {}
        elif extra:
            return {'response': ''}
        else:
            return ''


def http_excption_status_code(e):
    try:
        return e.response.status_code
    except:
        return -1


def using_replica(m, use_replica=True):
    if use_replica and settings.READ_REPLICA:
        return m.objects.using(settings.READ_REPLICA)
    else:
        return m.objects


def using_store_db(m):
    if settings.STORE_DATABASE:
        return m.objects.using(settings.STORE_DATABASE)
    else:
        return m.objects


def serializers_orders_fields():
    return ['id', 'order_id', 'line_id', 'source_id', 'source_status', 'source_type', 'source_tracking', 'created_at', 'updated_at']


def serializers_orders_track(tracks, store_type, humanize=False):
    orders = []
    for i in serializers.serialize('python', tracks, fields=serializers_orders_fields()):
        fields = i['fields']
        fields['id'] = i['pk']
        fields['store_type'] = store_type

        if humanize:
            fields['created_at'] = arrow.get(fields['created_at']).humanize()

        if not fields['source_type']:
            fields['source_type'] = 'aliexpress'

        if fields['source_id'] and ',' in fields['source_id']:
            for j in fields['source_id'].split(','):
                order_fields = deepcopy(fields)
                order_fields['source_id'] = j
                order_fields['bundle'] = True
                orders.append(order_fields)
        else:
            orders.append(fields)

    return orders


class CancelledOrderAlert():

    def __init__(self, user, source_id, new_status, current_status, order_track, store_type=''):
        self.user = user
        self.source_id = source_id
        self.new_source_status_details = new_status
        self.current_source_status_details = current_status
        self.order_track = order_track
        self.store_type = store_type

    def _can_email_cancelled_order(self):
        """
        This function checks if a cancellation e-mail can be send to the user
        after an order is cancelled at Aliexpress
        """
        if self.user.get_config('alert_order_cancelled') != 'notify':
            return False

        if self.new_source_status_details not in ALIEXPRESS_REJECTED_STATUS:
            return False

        if self.current_source_status_details in ALIEXPRESS_REJECTED_STATUS:
            return False

        return True

    def _send_cancelled_order_email(self):
        """
        Check for number of cancellation e-mails sent in the past 24 hours and
          - Send if there are less than 10 or
          - Send only one for higher
        """
        store_type = '{}_'.format(self.store_type) if self.store_type else ''

        cancelled_orders_key = '{}cancelled_orders_{}'.format(store_type, self.order_track.store_id)
        cancelled_orders_count = cache.get(cancelled_orders_key, 0)

        if cancelled_orders_count < 10:
            # Increase number of e-mails sent for cancelled orders
            cache.set(cancelled_orders_key, cancelled_orders_count + 1, timeout=86400)

            params = {'query': self.source_id, 'reason': self.new_source_status_details}
            send_email_from_template(
                tpl='aliexpress_order_cancellation.html',
                subject='[Dropified] Aliexpress Order has been Cancelled',
                recipient=self.user.email,
                data={
                    'username': self.user.username,
                    'track': self.order_track,
                    'track_url': app_link('{}/orders/track'.format(self.store_type), **params),
                },
            )
        elif cancelled_orders_count == 10:
            # Ensure no new e-mails are sent for 24 hours
            cache.set(cancelled_orders_key, cancelled_orders_count + 1, timeout=86400)

            params = {'reason': self.new_source_status_details}
            send_email_from_template(
                tpl='aliexpress_order_cancellation.html',
                subject='[Dropified] Many Aliexpress Orders has been Cancelled',
                recipient=self.user.email,
                data={
                    'username': self.user.username,
                    'track': self.order_track,
                    'track_url': app_link('{}/orders/track'.format(self.store_type), **params),
                    'bulk': True
                },
            )

    def send_email(self):
        if self._can_email_cancelled_order():
            self._send_cancelled_order_email()


def get_top_most_commons(most_commons):
    option, highest_count = most_commons[0]
    top_most_commons = []

    for most_common in most_commons:
        option, count = most_common
        if count == highest_count:
            top_most_commons.append(most_common)
            continue
        break

    return top_most_commons


def get_first_valid_option(most_commons, valid_options):
    for option, count in most_commons:
        if option in valid_options:
            return option


def slugify_menu(selected_menu):
    return selected_menu.replace(':', '-').replace('_', '-')


def bulk_order_format(queue_order, first_line_id):
    items_count = len(queue_order['items'])
    if items_count == 1:
        item = queue_order['items'][0]

        del queue_order['cart']
        del queue_order['items']

        queue_order.update(item)

        queue_order['url'] = re.sub(r'SACart=true&?', r'', queue_order['url'])

        return queue_order

    elif items_count > 1:
        line_item = queue_order['items'][0]
        queue_order['order_data'] = re.sub(r'_[^_]+$', '', line_item['order_data']) + '_' + str(first_line_id)
        queue_order['order_name'] = line_item['order_name']
        queue_order['order_id'] = line_item['order_id']

        queue_order['line_title'] = '<ul style="padding:0px;overflow-x:hidden;">'

        for line_item in queue_order['items'][:3]:
            queue_order['line_title'] += '<li>&bull; {}</li>'.format(line_item['line_title'])

        count = len(queue_order['items']) - 3
        if count > 0:
            queue_order['line_title'] += '<li>&bull; Plus {} Product{}...</li>'.format(count, pluralize(count))

        queue_order['line_title'] += '</ul>'

        return queue_order

    return None


def format_queueable_orders(request, orders, current_page, store_type='shopify'):
    orders_result = []
    next_page_url = None
    enable_supplier_grouping = False
    if store_type in ['shopify', '']:
        orders_place_url = reverse('orders_place')
    else:
        orders_place_url = reverse(f'{store_type}:orders_place')

    def group_by_supplier(lines):
        suppliers = {}
        for line in lines:
            if line.get('supplier') and line['supplier'].get_store_id():
                if line['supplier'].get_store_id() not in suppliers:
                    suppliers[line['supplier'].get_store_id()] = []

                suppliers[line['supplier'].get_store_id()].append(line)

        return suppliers

    for order in orders:
        if order.get('pending_payment', False):
            continue

        if order.get('is_fulfilled', False):
            continue

        line_items = dict_val(order, ['line_items', 'items'], [])

        if enable_supplier_grouping:
            line_items = group_by_supplier(line_items)
        else:
            line_items = {'all': line_items}

        for _supplier, group_lines in list(line_items.items()):
            queue_order = {"cart": True, "items": [], "line_id": []}
            first_line_id = None

            for line_item in group_lines:
                # Line item is not connected
                if not line_item.get('order_data_id') or not line_item.get('product'):
                    continue

                # Product is excluded from Dropified auto fulfill feature
                if hasattr(line_item['product'], 'is_excluded') and line_item['product'].is_excluded:
                    continue

                # Order is already placed (linked to a ShopifyOrderTrack)
                if line_item.get('order_track') and line_item['order_track'].id:
                    continue

                # Ignore items without a supplier
                if not line_item.get('supplier') or not line_item['supplier'].support_auto_fulfill():
                    continue

                # Do only aliexpress orders for now
                if not line_item['supplier'].is_aliexpress:
                    continue

                supplier = line_item['supplier']
                shipping_method = line_item.get('shipping_method') or {}
                line_data = {
                    'order_data': line_item.get('order_data_id'),
                    'order_name': order['name'],
                    'order_id': str(order['id']),
                    'line_id': str(line_item['id']),
                    'line_title': line_item['title'],
                    'store_type': store_type,
                    'source_id': str(supplier.get_source_id()),
                    'url': app_link(
                        orders_place_url,
                        supplier=supplier.id,
                        SAPlaceOrder=line_item.get('order_data_id'),
                        SACompany=shipping_method.get('method', ''),
                        SACountry=shipping_method.get('country', ''),
                        SACart='true',
                    ),
                }

                # Append bundle orders separately
                if line_item.get('is_bundle', False):
                    queue_bundle = {"cart": True, "items": [], "line_id": [], 'bundle': True}

                    for product in line_item['order_data']['products']:
                        # Do only aliexpress orders for now
                        if product['supplier_type'] != 'aliexpress':
                            continue

                        queue_bundle['items'].append({
                            **line_data,
                            'url': product['order_url'],
                            'line_title': product['title'],
                            'supplier_type': product['supplier_type'],
                            'product': product,
                        })
                        queue_bundle['line_id'].append(line_data['line_id'])

                    queue_bundle = bulk_order_format(queue_bundle, line_item['id'])
                    if queue_bundle is not None:
                        orders_result.append(queue_bundle)
                else:
                    if first_line_id is None:
                        first_line_id = line_item['id']

                    queue_order['items'].append(line_data)
                    queue_order['line_id'].append(line_data['line_id'])

            queue_order = bulk_order_format(queue_order, first_line_id)
            if queue_order is not None:
                orders_result.append(queue_order)

    page_end = safe_int(request.GET.get('page_end'), 0)
    page_start = safe_int(request.GET.get('page_start'), 1) - 1
    if current_page.has_next() and (not page_end or current_page.next_page_number() <= page_end):
        params = request.GET.copy()
        params['page'] = current_page.next_page_number() - page_start
        next_page_url = app_link(request.path, **params.dict())

    return JsonResponse({
        'orders': orders_result,
        'next': next_page_url,
        'pages': current_page.paginator.num_pages,
    })
