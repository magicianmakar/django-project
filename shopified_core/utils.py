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

from django.conf import settings
from django.core.mail import send_mail
from django.core.cache import cache
from django.contrib.auth.models import User
from django.template import Context, Template
from django.utils.crypto import get_random_string

import arrow
import bleach
import phonenumbers
from tld import get_tld


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


def hash_text(text):
    return hashlib.md5(text).hexdigest()


def random_hash():
    token = get_random_string(32)
    return hashlib.md5(token).hexdigest()


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


def hash_url_filename(s):
    url = remove_link_query(s)
    ext = get_fileext_from_url(s, fallback='jpg')

    if not re.match(r'(gif|jpe?g|png|ico|bmp)$', ext, re.I):
        ext = 'jpg'

    hashval = 0
    if (len(url) == 0):
        return hashval

    for i in range(len(url)):
        ch = ord(url[i])
        hashval = int(((hashval << 5) - hashval) + ch)
        hashval |= 0
    return '{}.{}'.format(ctypes.c_int(hashval & 0xFFFFFFFF).value, ext)


def get_mimetype(url, default=None):
    content_type = mimetypes.guess_type(remove_link_query(url))[0]
    return content_type if content_type else default


def send_email_from_template(tpl, subject, recipient, data, nl2br=True):
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

    send_mail(subject=subject,
              recipient_list=recipient,
              from_email='"Shopified App" <support@shopifiedapp.com>',
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
            'unlock_link': reverse('user_unlock', kwargs={'token': unlock_token})
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


def orders_update_limit(orders_count, check_freq=30, total_time=1440, min_count=20):
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
    else:
        country = customer_country

    if phone_number:
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
