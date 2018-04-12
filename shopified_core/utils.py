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

from django.conf import settings
from django.core.mail import send_mail
from django.core.cache import cache, caches
from django.contrib.auth.models import User
from django.template import Context, Template
from django.utils.crypto import get_random_string

import arrow
import bleach
import phonenumbers
from tld import get_tld


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
        app_link('order')
        app_link('order/track') or app_link('order', 'track')
        app_link('order/track', query=1001)
    """

    path = u'/'.join([str(i) for i in args]).lstrip('/') if args else ''

    if kwargs:
        for k, v in kwargs.items():
            if type(v) is bool:
                kwargs[k] = str(v).lower()

        path = u'{}?{}'.format(path, urlencode(kwargs))

    return u'{}/{}'.format(settings.APP_URL, path.lstrip('/')).rstrip('/')


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
        return 'http://{}'.format(url.lstrip(':/'))
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


def send_email_from_template(tpl, subject, recipient, data, nl2br=True, from_email=None):
    template_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'emails', tpl)
    template = Template(open(template_file).read())

    ctx = Context(data)

    email_html = template.render(ctx)

    if nl2br:
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

    send_mail(subject=subject,
              recipient_list=recipient,
              from_email=from_email,
              message=email_plain,
              html_message=email_html)

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
        if tries['count'] < 5:
            time.sleep(1)
            return False
        else:
            return True
    else:
        return False


def unlock_account_email(username):
    try:
        if '@' in username:
            user = User.objects.get(email__iexact=username)
        else:
            user = User.objects.get(username__iexact=username)
    except:
        return False

    from django.core.urlresolvers import reverse

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
        },
        nl2br=False
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
    new_username = username

    while User.objects.filter(username__iexact=new_username).exists():
        n += 1
        new_username = u'{}{}'.format(username.strip(), n)

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
