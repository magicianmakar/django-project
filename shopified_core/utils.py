import os
import re
import base64
import hashlib
import time
import hmac
import mimetypes
import urlparse
import ctypes
import simplejson as json
from urllib import urlencode
from functools import wraps
from copy import deepcopy

from django.conf import settings
from django.core import serializers
from django.core.mail import send_mail
from django.core.cache import cache, caches
from django.contrib.auth.models import User
from django.template import Context, Template
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
    "buyer_accept_goods": "Buyer Accept Goods",
    "seller_accept_issue_no_goods_return": "Seller Accept Issue No Goods Return",
    "seller_response_issue_timeout": "Seller Response Issue Timeout",
}


class OrderErrors:
    NAME = 1
    CITY = 2
    COUNTRY = 4


def safeInt(v, default=0):
    try:
        return int(v)
    except:
        return default


def safeFloat(v, default=0.0):
    try:
        return float(v)
    except:
        return default


def safeStr(v, default=''):
    """ Always return a str object """

    if isinstance(v, basestring):
        return v
    else:
        return default


def list_chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in xrange(0, len(l), n):
        yield l[i:i + n]


def app_link(*args, **kwargs):
    """
    Get full link to a web app page

    Example:
        app_link('orders')
        app_link('orders/track') or app_link('orders', 'track')
        app_link('orders/track', query=1001)
    """

    path = u'/'.join([str(i) for i in args]).lstrip('/') if args else ''

    if kwargs:
        for k, v in kwargs.items():
            if type(v) is bool:
                kwargs[k] = str(v).lower()
            elif isinstance(v, basestring):
                kwargs[k] = v.encode('utf-8')

        path = u'{}?{}'.format(path, urlencode(kwargs))

    return u'{}/{}'.format(settings.APP_URL, path.lstrip('/')).rstrip('/')


def remove_trailing_slash(t):
    t = safeStr(t, str(t))
    return t.strip('/')


def url_join(*args):
    url = [remove_trailing_slash(i) for i in args]
    return '/'.join(url).rstrip('/')


def hash_text(text):
    return hashlib.md5(text).hexdigest()


def hash_list(data, sep=''):
    return hash_text(sep.join([str(i) for i in data]))


def random_hash():
    token = get_random_string(32)
    return hashlib.md5(token).hexdigest()


def encode_params(val):
    val = val or ''
    return 'b:{}'.format(''.join(base64.encodestring(val).split('\n'))).strip()


def decode_params(val):
    if val:
        if val.startswith('b:'):
            return base64.decodestring(val[2:])

        elif not safeInt(val):
            try:
                r = base64.decodestring(val).decode('utf-8')
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

        return map(lambda k: k.split(sep), result) if top else result


def get_domain(url, full=False):
    if not url:
        return None

    if not url.startswith('http'):
        url = u'http://{}'.format(url)

    hostname = urlparse.urlparse(url).hostname
    if hostname is None:
        return hostname

    if full:
        return hostname
    else:
        return get_tld(url, as_object=True).domain


def add_http_schema(url):
    if not url.startswith('http'):
        return u'http://{}'.format(url.lstrip(':/'))
    else:
        return url


def remove_link_query(link):
    if not link:
        return ''

    if not link.startswith('http'):
        link = u'http://{}'.format(re.sub('^([:/]*)', r'', link))

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


def send_email_from_template(tpl, subject, recipient, data, nl2br=False, from_email=None, async=False):
    template_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'emails', tpl)
    template = Template(open(template_file).read())

    ctx = Context(data)

    email_html = template.render(ctx)

    if nl2br and '<head' not in email_html and '<body' not in email_html:
        email_plain = email_html
        email_html = email_html.replace('\n', '<br />')
    else:
        email_plain = bleach.clean(email_html, tags=[], strip=True).strip().split('\n')
        email_plain = map(lambda l: l.strip(), email_plain)
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

    if async:
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

    from django.urls import reverse

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
    string_to_sign = base64.encodestring(policy_str).replace('\n', '')

    signature = base64.encodestring(
        hmac.new(settings.AWS_SECRET_ACCESS_KEY.encode(), string_to_sign.encode('utf8'), hashlib.sha1).digest()).strip()

    return {
        'aws_available': aws_available,
        'aws_policy': string_to_sign,
        'aws_signature': signature,
    }


def clean_query_id(qid):
    ids = re.findall('([0-9]+)', qid)
    if len(ids):
        return safeInt(ids[0], 0)
    else:
        return 0


def version_compare(left, right):
    def normalize(v):
        return [int(x) for x in re.sub(r'(\.0+)*$', '', v).split(".")]

    return cmp(normalize(left), normalize(right))


def order_data_cache(*args, **kwargs):
    order_key = '_'.join([str(i) for i in args])

    if not order_key.startswith('order_'):
        order_key = 'order_{}'.format(order_key)

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
        fullname = u' '.join(fullname).strip()

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
        new_username = u'{}{}'.format(username.strip()[:29], n)

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


def encoded_dict(in_dict):
    out_dict = {}
    for k, v in in_dict.iteritems():
        if isinstance(v, unicode):
            v = v.encode('utf8')
        elif isinstance(v, str):
            # Must be encoded in UTF-8
            v.decode('utf8')
        out_dict[k] = v
    return out_dict


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
