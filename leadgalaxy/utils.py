import os
import simplejson as json
import requests
import hashlib
import pytz
import collections
import time
import base64
import boto
import datetime
import gzip
import hmac
import mimetypes
import re
import shutil
import tempfile
import ctypes
from urlparse import urlparse, parse_qs, urlsplit, urlunsplit
from urllib import urlencode
from hashlib import sha256
from math import ceil

from tld import get_tld
from boto.s3.key import Key

from django.conf import settings
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.core.paginator import Paginator
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.models import *
from shopified_core import permissions
from shopify_orders.models import ShopifyOrderLine


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


def get_domain(url, full=False):
    if not url:
        return None

    if not url.startswith('http'):
        url = u'http://{}'.format(url)

    hostname = urlparse(url).hostname
    if hostname is None:
        return hostname

    if full:
        return hostname
    else:
        return get_tld(url, as_object=True).domain


def upload_from_url(url, stores=[]):
    # Domains are taken from allowed stores plus store's CDN
    allowed_stores = stores + ['alicdn', 'aliimg', 'ebayimg', 'sunfrogshirts']
    allowed_paths = [r'^https?://s3.amazonaws.com/feather(-client)?-files-aviary-prod-us-east-1/']  # Aviary
    allowed_domains = ['%s.s3.amazonaws.com' % i for i in [settings.S3_STATIC_BUCKET, settings.S3_UPLOADS_BUCKET]]
    allowed_domains += ['cdn.shopify.com', 'shopifiedapp.s3.amazonaws.com', 'ecx.images-amazon.com',
                        'images-na.ssl-images-amazon.com', 'www.dhresource.com', 'd2kadg5e284yn4.cloudfront.net']

    allowed_mimetypes = ['image/jpeg', 'image/png', 'image/gif']

    can_pull = any([get_domain(url) in allowed_stores,
                    get_domain(url, full=True) in allowed_domains,
                    any([re.search(i, url) for i in allowed_paths])])

    mimetype = mimetypes.guess_type(remove_link_query(url))[0]

    return can_pull and mimetype in allowed_mimetypes


def remove_link_query(link):
    if not link:
        return ''

    if not link.startswith('http'):
        link = u'http://{}'.format(re.sub('^([:/]*)', r'', link))

    return re.sub('([?#].*)$', r'', link)


def get_mimetype(url):
    return mimetypes.guess_type(remove_link_query(url))[0]


def random_hash():
    token = get_random_string(32)
    return hashlib.md5(token).hexdigest()


def hash_text(text):
    return hashlib.md5(text).hexdigest()


def hash_list(data):
    return hash_text(''.join(data))


def random_filename(filename):
    ext = filename.split('.')[1:]
    return '{}.{}'.format(random_hash(), '.'.join(ext))


def generate_plan_registration(plan, data={}, bundle=None, sender=None):
    reg = PlanRegistration(plan=plan, bundle=bundle, sender=sender, email=data['email'], data=json.dumps(data))
    reg.register_hash = random_hash()
    reg.save()

    return reg


def get_plan(plan_hash=None, plan_slug=None):
    try:
        assert plan_hash != plan_slug

        if plan_hash:
            return GroupPlan.objects.get(register_hash=plan_hash)
        else:
            return GroupPlan.objects.get(slug=plan_slug)
    except:
        raven_client.captureMessage('Plan Not Found',
                                    extra={'plan_hash': plan_hash, 'plan_slug': plan_slug})

        return None


def apply_plan_registrations(email=''):
    registartions = PlanRegistration.objects.filter(expired=False)

    if email:
        registartions = registartions.filter(email__iexact=email)
    else:
        registartions = registartions.exclude(email='')

    for reg in registartions:
        if reg.get_usage_count() is not None:
            continue

        try:
            user = User.objects.get(email__iexact=reg.email)
            user.profile.apply_registration(reg, verbose=True)

        except User.DoesNotExist:
            # Not registred yet
            continue

        except Exception:
            raven_client.captureException(extra={'email': reg.email})
            continue


def apply_shared_registration(user, registration):
    usage = registration.get_usage_count()
    profile = user.profile

    usage['used'] = usage['used'] + 1

    if usage['used'] >= usage['allowed']:
        registration.expired = True

    registration.set_used_count(usage['used'])
    registration.add_user(profile.user.id)

    if registration.plan:
        print "REGISTRATIONS SHARED: Change user {} from '{}' to '{}'".format(user.email,
                                                                              profile.plan.title,
                                                                              registration.plan.title)

        if usage['expire_in_days']:
            expire_date = timezone.now() + timezone.timedelta(days=usage['expire_in_days'])

            profile.plan_after_expire = get_plan(plan_hash='606bd8eb8cb148c28c4c022a43f0432d')
            profile.plan_expire_at = expire_date

        profile.plan = registration.plan
        profile.save()

    elif registration.bundle:
        print "REGISTRATIONS SHARED: Add Bundle '{}' to: {} ({})".format(registration.bundle.title,
                                                                         user.username,
                                                                         user.email)

        profile.bundles.add(registration.bundle)

    registration.save()


def smart_board_by_product(user, product):
    product_info = json.loads(product.data)
    product_info = {
        'title': product_info.get('title', '').lower(),
        'tags': product_info.get('tags', '').lower(),
        'type': product_info.get('type', '').lower(),
    }

    for i in user.shopifyboard_set.all():
        try:
            config = json.loads(i.config)
        except:
            continue

        product_added = False
        for j in ['title', 'tags', 'type']:
            if product_added:
                break

            if not len(config.get(j, '')) or not len(product_info[j]):
                continue

            for f in config.get(j, '').split(','):
                if f.lower() in product_info[j]:
                    i.products.add(product)
                    product_added = True

                    break

        if product_added:
            i.save()


def smart_board_by_board(user, board):
    for product in user.shopifyproduct_set.all():
        product_info = json.loads(product.data)
        product_info = {
            'title': product_info.get('title', '').lower(),
            'tags': product_info.get('tags', '').lower(),
            'type': product_info.get('type', '').lower(),
        }

        try:
            config = json.loads(board.config)
        except:
            continue

        product_added = False
        for j in ['title', 'tags', 'type']:
            if product_added:
                break

            if not len(config.get(j, '')) or not len(product_info[j]):
                continue

            for f in config.get(j, '').split(','):
                if f.lower() in product_info[j]:
                    board.products.add(product)
                    product_added = True

                    break

        if product_added:
            board.save()


def format_data(data, title=True):
    text = ''
    for k, v in data.items():
        t = k
        if title:
            t = t.replace('_', ' ').title()
        text = u'{}    {}: {}\n'.format(text, t, v)

    return text.encode('utf-8')


def format_shopify_error(data):
    errors = data['errors']

    if isinstance(errors, basestring):
        return errors

    msg = []
    for k, v in errors.items():
        if type(v) is list:
            error = u','.join(v)
        else:
            error = v

        if k == 'base':
            msg.append(error)
        else:
            msg.append(u'{}: {}'.format(k, error))

    return u' | '.join(msg)


def verify_shopify_permissions(store):
    permissions = []

    r = requests.post(store.get_link('/admin/products.json', api=True))
    if r.status_code == 403:
        permissions.append('Products')

    r = requests.post(store.get_link('/admin/orders.json', api=True))
    if r.status_code == 403:
        permissions.append('Orders')

    r = requests.post(store.get_link('/admin/customers.json', api=True))
    if r.status_code == 403:
        permissions.append('Customers')

    r = requests.post(store.get_link('/admin/fulfillment_services.json', api=True))
    if r.status_code == 403:
        permissions.append('Fulfillment Service')

    r = requests.post(store.get_link('/admin/carrier_services.json', api=True))
    if r.status_code == 403:
        permissions.append('Shipping Rates')

    return len(permissions) == 0, permissions


def verify_shopify_webhook(store, request):
    api_secret = store.get_api_credintals().get('api_secret')
    webhook_hash = hmac.new(api_secret.encode(), request.body, sha256).digest()
    webhook_hash = base64.encodestring(webhook_hash).strip()

    assert webhook_hash == request.META.get('X-Shopify-Hmac-Sha256'), 'Webhook Verification'


def slack_invite(data, team='users'):
    slack_teams = {
        'users': {
            'token': settings.SLACK_USERS_TEAM_API,
            'channels': ['C0M6TTRAM', 'C0VN18AGP', 'C0LVBD3FD', 'C0V9EKPLG', 'C0V9P89S6',
                         'C0M6V41S4', 'C10RT5BFC', 'C0V7P4TTM'],
        },
        'ecom': {
            'token': settings.SLACK_ECOM_TEAM_API,
            'channels': ['C0X2GRYKB', 'C0X29Q308', 'C0X2AHJLV', 'C0X2AL0VB', 'C0X0USP5Z',
                         'C0RP77BL0', 'C0X0W91D1', 'C0X2N9JN6', 'C0RP35761', 'C0X0V4FL3',
                         'C0X27GL9W', 'C0Z90JQSG', 'C0X29D5C0', 'C11KP35SP', 'C0X0U3F6F'],
        }
    }

    try:
        r = requests.post(
            url='https://shopifiedapp.slack.com/api/users.admin.invite',
            data={
                'email': data['email'],
                'first_name': data['firstname'],
                'last_name': data['lastname'],
                'channels': ','.join(slack_teams[team]['channels']),
                'token': slack_teams[team]['token'],
                'set_active': True,
                '_attempts': 1
            }
        )

        rep = r.json()
        assert (rep['ok'] or rep.get('error') in ['already_invited', 'already_in_team']), 'Slack Invite Fail'

    except:
        raven_client.captureException()


def aliexpress_shipping_info(aliexpress_id, country_code):
    shippement_key = 'shipping_info_{}_{}'.format(aliexpress_id, country_code)
    shippement_data = cache.get(shippement_key)

    if shippement_data is not None:
        return shippement_data

    r = requests.get(url="http://freight.aliexpress.com/ajaxFreightCalculateService.htm",
                     timeout=10,
                     params={
                         'f': 'd',
                         'productid': aliexpress_id,
                         'userType': 'cnfm',
                         'country': country_code,
                         'province': '',
                         'city': '',
                         'count': '1',
                         'currencyCode': 'USD',
                         'sendGoodsCountry': ''
                     })

    try:
        shippement_data = json.loads(r.text[1:-1])
        cache.set(shippement_key, shippement_data, timeout=43200)
    except requests.exceptions.ConnectTimeout:
        raven_client.captureException(level='warning')
        cache.set(shippement_key, shippement_data, timeout=120)
        shippement_data = {}
    except:
        shippement_data = {}

    return shippement_data


def get_store_from_request(request):
    """
    Return ShopifyStore from based on `store` value or last saved store
    """

    store = None
    stores = request.user.profile.get_shopify_stores()

    if request.GET.get('shop'):
        try:
            store = stores.get(shop=request.GET.get('shop'))
        except (ShopifyStore.DoesNotExist, ShopifyStore.MultipleObjectsReturned):
            pass

    if not store and request.GET.get('store'):
        store = get_object_or_404(stores, id=safeInt(request.GET.get('store')))

    if store:
        permissions.user_can_view(request.user, store)
        request.session['last_store'] = store.id
    else:
        try:
            if 'last_store' in request.session:
                store = stores.get(id=request.session['last_store'])
                permissions.user_can_view(request.user, store)

        except (PermissionDenied, ShopifyStore.DoesNotExist):
            store = None

    if not store:
        store = stores.first()

    return store


def get_myshopify_link(user, default_store, link):
    stores = [default_store, ]
    for i in user.profile.get_shopify_stores():
        if i not in stores:
            stores.append(i)

    for store in stores:
        handle = link.split('/')[-1]

        r = requests.get(store.get_link('/admin/products.json', api=True), params={'handle': handle}).json()
        if len(r['products']) == 1:
            return store.get_link('/admin/products/{}'.format(r['products'][0]['id']))

    return None


def get_shopify_id(url):
    ''' Get Shopify Product ID from a url '''
    if url and url.strip():
        try:
            if '/variants/' in url:
                return safeInt(re.findall('products/([0-9]+)/variants', url)[0])
            else:
                return safeInt(re.findall('products/([0-9]+)$', url)[0])
        except:
            return 0
    else:
        return 0


def get_store_from_url(user, url):
    domain = get_domain(url, full=True)
    return ShopifyStore.objects.filter(api_url__icontains=domain, user=user).first()


def duplicate_product(product, store=None):
    parent_product = ShopifyProduct.objects.get(id=product.id)

    product.pk = None
    product.parent_product = parent_product
    product.shopify_id = 0

    if store is not None:
        product.store = store

    product.save()

    for i in parent_product.productsupplier_set.all():
        i.pk = None
        i.product = product
        i.store = product.store
        i.save()

        if i.is_default:
            product.set_default_supplier(i, commit=True)

    return product


def split_product(product, split_factor, store=None):
    data = json.loads(product.data)
    new_products = []

    if data['variants'] and len(data['variants']):
        active_variant = None
        filtered = [v for v in data['variants'] if v['title'] == split_factor]
        if len(filtered) > 0:
            active_variant = filtered[0]

        if active_variant:
            for idx, v in enumerate(active_variant['values']):
                clone = ShopifyProduct.objects.get(id=product.id)
                clone.pk = None
                clone.parent_product = product
                clone.shopify_id = 0

                new_data = json.loads(clone.data)
                new_images = []
                for img in new_data['images']:
                    hashval = hash_url_filename(img)
                    if not (hashval in new_data['variants_images'] and new_data['variants_images'][hashval] in active_variant['values']):
                        new_images.append(img)
                    if hashval in new_data['variants_images'] and new_data['variants_images'][hashval] == v:
                        new_images.insert(0, img)
                new_data['images'] = new_images
                new_data['variants'] = [v1 for v1 in new_data['variants'] if v1['title'] != split_factor]
                # new_data['variants'].append({'title': split_factor, 'values': [v]})
                new_data['title'] = u'{}, {} - {}'.format(data['title'], active_variant['title'], v)

                clone.data = json.dumps(new_data)

                if store is not None:
                    clone.store = store

                clone.save()

                for i in product.productsupplier_set.all():
                    i.pk = None
                    i.product = clone
                    i.store = clone.store
                    i.save()

                    if i.is_default:
                        clone.set_default_supplier(i, commit=True)

                new_products.append(clone)

    return new_products


def get_shopify_products_count(store):
    return requests.get(url=store.get_link('/admin/products/count.json', api=True)).json().get('count', 0)


def get_shopify_products(store, page=1, limit=50, all_products=False,
                         product_ids=None, fields=None, session=requests):

    if not all_products:
        params = {
            'page': page,
            'limit': limit
        }

        if product_ids:
            if type(product_ids) is list:
                params['ids'] = ','.join(product_ids)
            else:
                params['ids'] = product_ids

        if fields:
            if type(fields) is list:
                params['fields'] = ','.join(fields)
            else:
                params['fields'] = fields

        rep = session.get(
            url=store.get_link('/admin/products.json', api=True),
            params=params
        )

        rep = rep.json()

        for p in rep['products']:
            yield p
    else:
        limit = 200
        count = get_shopify_products_count(store)

        if not count:
            return

        pages = int(ceil(count / float(limit)))
        for page in xrange(1, pages + 1):
            rep = get_shopify_products(store=store, page=page, limit=limit,
                                       all_products=False, session=requests.session())
            for p in rep:
                yield p


def get_shopify_product(store, product_id, raise_for_status=False):
    if store:
        rep = requests.get(url=store.get_link('/admin/products/{}.json'.format(product_id), api=True))

        if raise_for_status:
            rep.raise_for_status()

        return rep.json().get('product')
    else:
        return None


def get_product_images_dict(store, product):
    images = {}
    product = get_shopify_product(store, product)

    if not product:
        return images

    for i in product['images']:
        for var in i['variant_ids']:
            images[var] = i['src']

    # Default image
    images[0] = product.get('image').get('src') if product.get('image') else ''

    return images


def link_product_images(product):
    for i in product.get('images', []):
        for var in i['variant_ids']:
            for idx, el in enumerate(product['variants']):
                if el['id'] == var:
                    product['variants'][idx]['image_src'] = i['src']

    return product


def get_shopify_variant_image(store, product_id, variant_id):
    """ product_id: Product ID in Shopify """
    product_id = safeInt(product_id)
    variant_id = safeInt(variant_id)
    image = None

    if not product_id:
        return None

    try:
        cached = ShopifyProductImage.objects.get(store=store, product=product_id, variant=variant_id)
        return cached.image
    except:
        pass

    images = get_product_images_dict(store, product_id)

    if variant_id and variant_id in images:
        image = images[variant_id]

    if not image:
        image = images.get(0)  # Default image

    if image:
        cached = ShopifyProductImage(store=store, product=product_id, variant=variant_id, image=image)
        cached.save()

        return image
    else:
        return None


def get_shopify_order(store, order_id):
    rep = requests.get(store.get_link('/admin/orders/{}.json'.format(order_id), api=True))
    rep.raise_for_status()

    return rep.json()['order']


def get_shopify_order_line(store, order_id, line_id, line_sku=None, note=False):
    order = get_shopify_order(store, order_id)
    for line in order['line_items']:
        if line_id and int(line['id']) == int(line_id):
            if note:
                return line, order['note']
            else:
                return line

        elif line_sku and line['sku'] == line_sku:
            if note:
                return line, order['note']
            else:
                return line

    if note:
        return None, None
    else:
        return None


def get_shopify_order_note(store, order_id):
    order = get_shopify_order(store, order_id)
    return order['note']


def set_shopify_order_note(store, order_id, note):
    rep = requests.put(
        url=store.get_link('/admin/orders/{}.json'.format(order_id), api=True),
        json={
            'order': {
                'id': order_id,
                'note': note[:5000]
            }
        }
    )

    response = rep.text
    rep.raise_for_status()

    if rep.ok:
        response = rep.json()

    return response['order']['id']


def add_shopify_order_note(store, order_id, new_note, current_note=False):
    if current_note is False:
        note = get_shopify_order_note(store, order_id)
    else:
        note = current_note

    if note:
        note = '{}\n{}'.format(note.encode('utf-8'), new_note.encode('utf-8'))
    else:
        note = new_note

    return set_shopify_order_note(store, order_id, note)


def shopify_link_images(store, product):
    """
    Link Shopify variants with their images
    """

    mapping = {}
    mapping_idx = {}
    for key, val in enumerate(product[u'images']):
        var = re.findall('/v-(.+)__', val[u'src'])

        if len(var) != 1:
            continue

        mapping[var[0]] = val['id']
        mapping_idx[var[0]] = key

    if not len(mapping_idx):
        return None

    for key, val in enumerate(product[u'variants']):
        for option in [val['option1'], val['option2'], val['option3']]:
            if not option:
                continue

            option = re.sub('[^A-Za-z0-9 _-]', '', option)
            option = re.sub(' +', '_', option)

            img_idx = mapping_idx.get(option)

            if not img_idx:
                continue

            if val['id'] not in product['images'][img_idx]['variant_ids']:
                product['images'][img_idx]['variant_ids'].append(val['id'])

    api_product = {
        'id': product['id'],
        'images': []
    }

    for image in product['images']:
        api_product['images'].append({
            'id': image['id'],
            'variant_ids': image['variant_ids'],
        })

    return requests.put(
        url=store.get_link('/admin/products/{}.json'.format(product['id']), api=True),
        json={'product': api_product}
    )


def webhook_token(store_id):
    return hashlib.md5('{}-{}'.format(store_id, settings.SECRET_KEY)).hexdigest()


def create_shopify_webhook(store, topic):
    token = webhook_token(store.id)
    endpoint = store.get_link('/admin/webhooks.json', api=True)
    data = {
        'webhook': {
            'topic': topic,
            'format': 'json',
            'address': 'http://app.shopifiedapp.com/webhook/shopify/{}?store={}&t={}'.format(topic.replace('/', '-'), store.id, token)
        }
    }

    try:
        rep = requests.post(endpoint, json=data)
        webhook_id = rep.json()['webhook']['id']

        webhook = ShopifyWebhook(store=store, token=token, topic=topic, shopify_id=webhook_id)
        webhook.save()

        return webhook
    except:
        raven_client.captureException()
        return None


def get_shopify_webhook(store, topic):
    try:
        return ShopifyWebhook.objects.get(store=store, topic=topic)
    except ShopifyWebhook.DoesNotExist:
        return None
    except ShopifyWebhook.MultipleObjectsReturned:
        raven_client.captureException()
        return ShopifyWebhook.objects.filter(store=store, topic=topic).first()
    except:
        raven_client.captureException()
        return None


def attach_webhooks(store):
    default_topics = [
        'app/uninstalled', 'shop/update', 'products/update',
        'products/delete', 'orders/create', 'orders/updated', 'orders/delete']

    webhooks = []

    if settings.DEBUG:
        return webhooks

    for topic in default_topics:
        webhook = get_shopify_webhook(store, topic)

        if not webhook:
            webhook = create_shopify_webhook(store, topic)

        if webhook:
            webhooks.append(webhook)

    return webhooks


def detach_webhooks(store, delete_too=False):
    if settings.DEBUG:
        return

    for webhook in store.shopifywebhook_set.all():
        webhook.detach()

        if delete_too:
            webhook.delete()


def get_tracking_orders(store, tracker_orders):
    ids = []
    for i in tracker_orders:
        ids.append(str(i.order_id))

    params = {
        'status': 'any',
        'ids': ','.join(ids),
    }

    rep = requests.get(
        url=store.get_link('/admin/orders.json', api=True),
        params=params
    )

    if not rep.ok:
        return tracker_orders

    orders = {}
    lines = {}

    for order in rep.json()['orders']:
        orders[order['id']] = order
        for line in order['line_items']:
            try:
                lines['{}-{}'.format(order['id'], line['id'])] = line
            except:
                pass

    new_tracker_orders = []
    for tracked in tracker_orders:
        tracked.order = orders.get(tracked.order_id)
        tracked.line = lines.get('{}-{}'.format(tracked.order_id, tracked.line_id))

        if tracked.line:
            fulfillment_status = tracked.line.get('fulfillment_status')
            manual_fulfillement = tracked.line.get('fulfillment_service') == 'manual'

            if not fulfillment_status:
                fulfillment_status = ''

            if manual_fulfillement and tracked.shopify_status != fulfillment_status:
                tracked.shopify_status = fulfillment_status
                tracked.save()

        new_tracker_orders.append(tracked)

    return new_tracker_orders


def is_valide_tracking_number(tarcking_number):
    return tarcking_number and re.match('^[0-9]+$', tarcking_number) is None


def is_chinese_carrier(tarcking_number):
    return tarcking_number and re.search('(CN|SG|HK)$', tarcking_number) is not None


def shipping_carrier(tracking_number):
    patterns = [{
        'name': "Royal Mail",
        'pattern': "^([A-Z]{2}\\d{9}GB)$"
    }, {
        'name': "UPS",
        'pattern': "^(1Z)|^(K\\d{10}$)|^(T\\d{10}$)"
    }, {
        'name': "Canada Post",
        'pattern': "((CA)$|^\\d{16}$)"
    }, {
        'name': "China Post",
        'pattern': "^(R|CP|E|L)\\w+CN$"
    }, {
        'name': "FedEx",
        'pattern': "^(\\d{12}$)|^(\\d{15}$)|^(96\\d{20}$)|^(7489\\d{16}$)"
    }, {
        'name': "Post Danmark",
        'pattern': "\\d{3}5705983\\d{10}|DK$"
    }, {
        'name': "USPS",
        'pattern': "^((?:94001|92055|94073|93033|92701|94055|92088|92021|92001|94108|"
                   "93612|94701|94058|94490)\\d{17}|7\\d{19}|03\\d{18}|8\\d{9}|420"
                   "\\d{23,27}|10169\\d{11}|[A-Z]{2}\\d{9}US|(?:EV|CX)\\d{9}CN|LK\\d{9}HK)$"
    }, {
        'name': "FedEx UK",
        'pattern': None
    }, {
        'name': "DHL",
        'pattern': "^(\\d{10,11}$)"
    }, {
        'name': "DHL eCommerce",
        'pattern': "^(GM\\d{16,18}$)|^([A-Z0-9]{14}$)|^(\\d{22}$)"
    }, {
        'name': "DHL eCommerce Asia",
        'pattern': "^P[A-Z0-9]{14}$"
    }, {
        'name': "Eagle",
        'pattern': None
    }, {
        'name': "Purolator",
        'pattern': "^[A-Z]{3}\\d{9}$"
    }, {
        'name': "TNT",
        'pattern': None
    }, {
        'name': "Australia Post",
        'pattern': "^([A-Z]{2}\\d{9}AU)$"
    }, {
        'name': "New Zealand Post",
        'pattern': "^[A-Z]{2}\\d{9}NZ$"
    }, {
        'name': "TNT Post",
        'pattern': "^\\w{13}$"
    }, {
        'name': "4PX",
        'pattern': "^RF\\d{9}SG$|^RT\\d{9}HK$|^7\\d{10}$|^P0{4}\\d{8}$|^JJ\\d{9}GB$|^MS\\d{8}XSG$"
    }, {
        'name': "APC",
        'pattern': "^PF\\d{11}$|^\\d{13}$"
    }, {
        'name': "FSC",
        'pattern': "^((?:LS|LM|RW|RS|RU|RX)\\d{9}(?:CN|CH|DE)|(?:WU\\d{13})|(?:\\w{10}$|\\d{22}))$"
    }, {
        'name': "Globegistics",
        'pattern': "^JJ\\d{9}GB$|^(LM|CJ|LX|UM|LJ|LN)\\d{9}US$|^(GAMLABNY|"
                   "BAIBRATX|SIMGLODE)\\d{10}$|^\\d{10}$"
    }, {
        'name': "Amazon Logistics US",
        'pattern': "^TBA\\d{12,13}$"
    }, {
        'name': "Amazon Logistics UK",
        'pattern': "^Q\\d{11,13}$"
    }, {
        'name': "Bluedart",
        'pattern': "^\\d{9,11}$"
    }, {
        'name': "Delhivery",
        'pattern': "^\\d{11,12}$"
    }, {
        'name': "Japan Post",
        'pattern': "^[a-z]{2}\\d{9}JP|^\\d{11}$"
    }]

    for p in patterns:
        if p['pattern'] and re.search(p['pattern'], tracking_number):
            return p['name']

    return None


def order_track_fulfillment(**kwargs):
    ''' Get Tracking Carrier and Url for Shopify Order Fulfillment
        order_id:        Shopify Order ID
        line_id:         Shopify Order Line
        source_tracking: Order Tracking Number
        order_track:     ShopifyOrderTrack to get above args. from (optional)
        user_config:     UserProfile config dict
    '''

    if kwargs.get('order_track'):
        order_id = kwargs.get('order_track').order_id
        line_id = kwargs.get('order_track').line_id
        source_tracking = kwargs.get('order_track').source_tracking
        store_id = kwargs.get('order_track').store_id
    else:
        order_id = kwargs['order_id']
        line_id = kwargs['line_id']
        source_tracking = kwargs['source_tracking']
        store_id = safeInt(kwargs.get('store_id'))

        if not len(source_tracking):
            source_tracking = None

    user_config = kwargs['user_config']

    is_usps = False
    line = None

    try:
        if kwargs.get('use_usps') is None:  # Find line when shipping method is not selected
            line = ShopifyOrderLine.objects.select_related('order').get(
                line_id=line_id,
                order__store_id=store_id,
                order__order_id=order_id)

            is_usps = (is_chinese_carrier(source_tracking) or shipping_carrier(source_tracking) == 'USPS') \
                and line.order.country_code == 'US'

    except ShopifyOrderLine.DoesNotExist:
        pass
    except:
        raven_client.captureException()

    data = {
        "fulfillment": {
            "tracking_number": source_tracking,
            "line_items": [{
                "id": line_id,
            }]
        }
    }

    if source_tracking:
        have_custom_domain = store_id and type(user_config.get('aftership_domain')) is dict

        if (kwargs.get('use_usps') is None and is_usps and not have_custom_domain) or kwargs.get('use_usps'):
            data['fulfillment']['tracking_company'] = "USPS"
        else:
            aftership_domain = 'http://track.aftership.com/{{tracking_number}}'

            if have_custom_domain:
                aftership_domain = user_config.get('aftership_domain').get(str(store_id), aftership_domain)
                if '{{tracking_number}}' not in aftership_domain:
                    aftership_domain = "http://{}.aftership.com/{{{{tracking_number}}}}".format(aftership_domain)
                elif not aftership_domain.startswith('http'):
                    aftership_domain = 'http://{}'.format(re.sub('^([:/]*)', r'', aftership_domain))

            data['fulfillment']['tracking_company'] = "Other"
            data['fulfillment']['tracking_url'] = aftership_domain.replace('{{tracking_number}}', source_tracking)

    if user_config.get('validate_tracking_number', True) \
            and not is_valide_tracking_number(source_tracking) \
            and not is_usps:
        notify_customer = 'no'
    else:
        notify_customer = user_config.get('send_shipping_confirmation', 'default')

    if notify_customer == 'default':
        if line:
            if line.order.items_count <= 1:
                data['fulfillment']['notify_customer'] = True
            else:
                fulfilled = line.order.shopifyorderline_set.filter(fulfillment_status='fulfilled').exclude(id=line.id).count()
                data['fulfillment']['notify_customer'] = (line.order.items_count <= fulfilled + 1)

                line.fulfillment_status = 'fulfilled'
                line.save()
        else:
            data['fulfillment']['notify_customer'] = True
    else:
        data['fulfillment']['notify_customer'] = (notify_customer == 'yes')

    return data


def get_variant_name(variant):
    options = re.findall('#([^;:]+)', variant.get('variant_desc', ''))
    if len(options):
        return ' / '.join([i.title() for i in options])
    else:
        name = variant.get('variant_id')
        return name if name else '<Default>'


def get_mapping_from_product(product):
    var_map = {}

    for v in product['variants']:
        options = filter(lambda j: bool(j), [v['option1'], v['option2'], v['option3']])

        if len(options):
            options = map(lambda j: {'title': j}, options)

            var_map[str(v['id'])] = options

    return var_map


def product_changes_remap(changes):

    remapped = {
        'product': {
            'offline': [],
        },
        'variants': {
            'quantity': [],
            'price': [],
            'new': [],
            'removed': [],
        }
    }

    products = changes['changes'].get('product')
    if products and len(products):
        for i in products:
            remapped['product']['offline'].append({
                'category': i['category'],
                'new_value': i['new_value'],
                'old_value': i['old_value'],
            })

    variants = changes['changes'].get('variants')
    if variants and len(variants):
        for i in variants:
            if not i or not i.get('changes'):
                continue

            for change in i.get('changes'):
                if change['category'] == 'Availability':
                    remapped['variants']['quantity'].append({
                        'category': change['category'],
                        'new_value': change['new_value'],
                        'old_value': change['old_value'],
                        'variant_desc': get_variant_name(i),
                        'variant_id': i['variant_id'],
                    })
                if change['category'] == 'Price':
                    remapped['variants']['price'].append({
                        'category': change['category'],
                        'new_value': change['new_value'],
                        'old_value': change['old_value'],
                        'variant_desc': get_variant_name(i),
                        'variant_id': i['variant_id'],
                    })
                if change['category'] == 'new':
                    remapped['variants']['new'].append({
                        'category': change['category'],
                        'price': change['price'],
                        'quantity': change['quantity'],
                        'variant_desc': get_variant_name(i),
                        'variant_id': i['variant_id'],
                    })
                if change['category'] == 'removed':
                    remapped['variants']['removed'].append({
                        'category': change['category'],
                        'price': change['price'],
                        'quantity': change['quantity'],
                        'variant_desc': get_variant_name(i),
                        'variant_id': i['variant_id'],
                    })

    return remapped


def object_dump(obj, desc=None):
    if desc:
        print 'object_dump'
        print '==========='
        print desc, '=', json.dumps(obj, indent=4)
        print '==========='
        print
    else:
        print json.dumps(obj, indent=4)


def jvzoo_verify_post(params):
    """Verifies if received POST is a valid JVZoo POST request.

    :param params: POST parameters sent by JVZoo Notification Service
    :type params: dict"""

    if not settings.JVZOO_SECRET_KEY:
        raise Exception('JVZoo secret-key is not set.')

    strparams = u""

    for key in iter(sorted(params.iterkeys())):
        if key in ['cverify', 'secretkey']:
            continue
        strparams += params[key] + "|"
    strparams += settings.JVZOO_SECRET_KEY
    sha = hashlib.sha1(strparams.encode('utf-8')).hexdigest().upper()
    assert params['cverify'] == sha[:8], 'Checksum verification failed. ({} <> {})'.format(params['cverify'], sha[:8])


def jvzoo_parse_post(params):
    """Parse POST from JVZoo and extract information we need.

    :param params: POST parameters sent by JVZoo Notification Service
    :type params: dict """

    return {
        'email': params['ccustemail'],
        'fullname': params['ccustname'],
        'firstname': params['ccustname'].split(' ')[0],
        'lastname': ' '.join(params['ccustname'].split(' ')[1:]),
        'product_id': params['cproditem'],
        'affiliate': params['ctransaffiliate'],
        'trans_type': params['ctransaction'],
    }


def zaxaa_verify_post(params):
    """ Verifies if received POST is a valid Zaxaa POST request. """

    if not settings.ZAXAA_API_SIGNATURE:
        raise Exception('Zaxaa secret-key is not set.')

    strparams = u"{}{}{}{}".format(
        params['seller_id'],
        settings.ZAXAA_API_SIGNATURE,
        params['trans_receipt'],
        params['trans_amount']
    ).upper()

    post_hash = hashlib.md5(strparams.encode('utf-8')).hexdigest().upper()
    assert params['hash_key'] == post_hash, 'Checksum verification failed. ({} <> {})'.format(params['hash_key'], post_hash)


def zaxaa_parse_post(params):
    """ Parse POST from Zaxaa and extract information we need.

    :param params: POST parameters sent by Zaxaa Notification Service
    :type params: dict """

    return {
        'email': params['cust_email'],
        'fullname': u'{} {}'.format(params['cust_firstname'], params['cust_lastname']),
        'firstname': params['cust_firstname'],
        'lastname': params['cust_lastname'],
        'product_id': params['products[0][prod_number]'],
        'affiliate': '',
        'trans_type': params['trans_type'],
    }


def set_url_query(url, param_name, param_value):
    """
    Given a URL, set or replace a query parameter and return the modified URL.
    """

    scheme, netloc, path, query_string, fragment = urlsplit(url)
    query_params = parse_qs(query_string)
    query_params[param_name] = [param_value]
    new_query_string = urlencode(query_params, doseq=True)
    return urlunsplit((scheme, netloc, path, new_query_string, fragment))


def affiliate_link_set_query(url, name, value):
    if '/deep_link.htm' in url:
        dl_target_url = parse_qs(urlparse(url).query)['dl_target_url'].pop()
        dl_target_url = set_url_query(dl_target_url, name, value)

        return set_url_query(url, 'dl_target_url', dl_target_url)
    elif 'alitems.com' in url:
        if name != 'ulp':
            ulp = parse_qs(urlparse(url).query)['ulp'].pop()
            ulp = set_url_query(ulp, name, value)

            return set_url_query(url, 'ulp', ulp)
        else:
            return set_url_query(url, name, value)
    else:
        return set_url_query(url, name, value)


def get_aliexpress_credentials(user):
    user_credentials = True

    if user.can('aliexpress_affiliate.use'):
        api_key, tracking_id = user.get_config([
            'aliexpress_affiliate_key',
            'aliexpress_affiliate_tracking'
        ])
    else:
        api_key, tracking_id = (None, None)

    if not api_key or not tracking_id:
        user_credentials = False
        api_key, tracking_id = ['37954', 'shopifiedapp']

    return api_key, tracking_id, user_credentials


def get_admitad_credentials(user):
    user_credentials = True

    if user.can('admitad_affiliate.use'):
        site_id = user.get_config('admitad_site_id')
    else:
        site_id = None

    if not site_id:
        user_credentials = False
        site_id = '1e8d114494c02ea3d6a016525dc3e8'

    return site_id, user_credentials


def get_admitad_affiliate_url(site_id, url):
    api_url = 'https://alitems.com/g/{}/'.format(site_id)

    return affiliate_link_set_query(api_url, 'ulp', url)


def get_aliexpress_affiliate_url(appkey, trackingID, urls, services='ali'):
    promotion_key = 'promotion_links__{}'.format(hash_text(urls))
    promotion_url = cache.get(promotion_key)

    if promotion_url is not None:
        return promotion_url

    rep = None

    try:
        r = requests.get(
            url='http://gw.api.alibaba.com/openapi/param2/2/portals.open/api.getPromotionLinks/{}'.format(appkey),
            params={
                'fields': 'publisherId,trackingId,promotionUrls',
                'trackingId': trackingID,
                'urls': urls

            },
            timeout=5
        )

        rep = r.text
        r = r.json()

        errorCode = r['errorCode']
        if errorCode != 20010000:
            raven_client.captureMessage('Aliexpress Promotion Error',
                                        extra={'errorCode': errorCode, 'response': r},
                                        level='warning')
            return None

        if len(r['result']['promotionUrls']):
            promotion_url = r['result']['promotionUrls'][0]['promotionUrl']
            if promotion_url:
                cache.set(promotion_key, promotion_url, timeout=43200)

            return promotion_url
        else:
            raven_client.captureMessage('Aliexpress Promotion Not Found',
                                        extra={'response': r, 'product': urls},
                                        level='warning')

            cache.set(promotion_key, False, timeout=3600)
            return None

    except:
        cache.set(promotion_key, False, timeout=3600)
        raven_client.captureException(level='warning', extra={'response': rep})

    return None


def get_countries():
    country_names = pytz.country_names
    country_names = collections.OrderedDict(sorted(country_names.items(), key=lambda i: i[1]))
    countries = zip(country_names.keys(), country_names.values())

    return countries


def get_timezones(country=None):
    if country:
        zones = pytz.country_timezones(country)
    else:
        zones = pytz.common_timezones

    timezones = []
    for i in zones:
        offset = datetime.datetime.now(pytz.timezone(i)).strftime('%z')
        offset = re.sub(r'([^0-9])([0-9]{2})([0-9]{2})', r'\1\2:\3', offset)
        # offset = re.sub(r':00$', '', offset)

        name = i.replace('_', ' ')
        if country == 'US' and name.startswith('America/'):
            name = name.replace('America/', '')

        timezones.append([
            i,
            '{} ({})'.format(name, offset)
        ])

    return timezones


def fix_product_url(data, request):
    if 'product' in data:
        if not data['product']['url'].startswith('http'):
            data['product']['url'] = request.build_absolute_uri(data['product']['url'])

    return data


def clean_query_id(qid):
    ids = re.findall('([0-9]+)', qid)
    if len(ids):
        return safeInt(ids[0], 0)
    else:
        return 0


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


def get_orders_filter(request, name=None, default=None, checkbox=False):
    if name:
        key = '_orders_filter_{}'.format(name)
        val = request.GET.get(name)

        if not val:
            val = request.user.get_config(key, default)

        return val
    else:
        filters = {}
        for name, val in request.user.profile.get_config().items():
            if name.startswith('_orders_filter_'):
                filters[name.replace('_orders_filter_', '')] = val

        return filters


def set_orders_filter(user, filters, default=None):
    fields = ['sort', 'status', 'fulfillment', 'financial',
              'desc', 'connected', 'awaiting_order']

    for name, val in filters.items():
        if name in fields:
            key = '_orders_filter_{}'.format(name)
            user.set_config(key, val)


def aws_s3_get_key(filename, bucket_name=None):
    if bucket_name is None:
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME

    conn = boto.connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_ACCESS_KEY)
    bucket = conn.get_bucket(bucket_name)

    return bucket.get_key(filename)


def aws_s3_upload(filename, content=None, fp=None, input_filename=None, mimetype=None,
                  upload_time=False, compress=False, bucket_name=None):
    """
    Store an object in S3 using the 'filename' as the key in S3 and the
    contents of the file pointed to by either 'fp' or 'content' as the
    contents.
    """

    if upload_time:
        upload_start = time.time()

    if bucket_name is None:
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME

    conn = boto.connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_ACCESS_KEY)
    bucket = conn.get_bucket(bucket_name)
    k = Key(bucket)

    if not mimetype:
        mimetype = mimetypes.guess_type(filename)[0]

    k.key = filename
    k.set_metadata("Content-Type", mimetype)

    if not fp and not input_filename and not content:
        raise Exception('content or fp parameters are both empty')

    if not compress:
        if content:
            k.set_contents_from_string(content)

        elif input_filename:
            k.set_contents_from_filename(input_filename)

        elif fp:
            k.set_contents_from_file(fp)
    else:
        tmp_file = tempfile.NamedTemporaryFile(mode="wb", suffix=".gz", delete=False)

        if fp:
            with open(fp.name, 'rb') as f_in:
                with gzip.open(tmp_file.name, 'wb') as gz_out:
                    shutil.copyfileobj(f_in, gz_out)

        if input_filename:
            with open(input_filename, 'rb') as f_in:
                with gzip.open(tmp_file.name, 'wb') as gz_out:
                    shutil.copyfileobj(f_in, gz_out)

        elif content:
            with gzip.open(tmp_file.name, 'wb') as gz_out:
                gz_out.write(content.encode('utf-8'))

        k.set_metadata('Content-Encoding', 'gzip')
        k.set_contents_from_filename(tmp_file.name)

        # Clean up the temp file
        os.unlink(tmp_file.name)

    k.make_public()

    upload_url = 'https://%s.s3.amazonaws.com/%s' % (bucket_name, filename)

    if upload_time:
        return upload_url, time.time() - upload_start
    else:
        return upload_url


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


# Helper Classes

class TimezoneMiddleware(object):

    def process_request(self, request):
        tzname = request.session.get('django_timezone')
        if not tzname:
            if request.user.is_authenticated():
                tzname = request.user.profile.timezone
                request.session['django_timezone'] = request.user.profile.timezone

        if tzname:
            timezone.activate(pytz.timezone(tzname))
        else:
            timezone.deactivate()


class ShopifyOrderPaginator(Paginator):
    reverse_order = False
    query = None

    def set_store(self, store):
        self.store = store

    def set_filter(self, status, fulfillment, financial):
        self.status = status
        self.fulfillment = fulfillment
        self.financial = financial

    def set_order_limit(self, limit):
        self.order_limit = limit

    def set_current_page(self, page):
        self.current_page = page

    def set_reverse_order(self, reverse_order):
        self.reverse_order = reverse_order

    def set_query(self, query):
        self.query = query

    def page(self, number):
        """
        Returns a Page object for the given 1-based page number.
        """

        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page
        if top + self.orphans >= self.count:
            top = self.count

        self.set_current_page(number)

        api_page = number
        orders = self.get_orders(api_page)

        return self._get_page(orders, number, self)

    def page_range(self):
        """
        Returns a 1-based range of pages for iterating through within
        a template for loop.
        """
        page_count = self.num_pages

        pages = range(max(1, self.current_page - 5), self.current_page) + range(self.current_page, min(page_count + 1, self.current_page + 5))
        if 1 not in pages:
            pages = [1, None] + pages

        if page_count not in pages:
            pages = pages + [None, page_count]

        return pages

    def get_orders(self, page):
        if self.reverse_order:
            sorting = 'asc'
        else:
            sorting = 'desc'

        params = {
            'limit': self.order_limit,
            'page': page,
            'status': self.status,
            'fulfillment_status': self.fulfillment,
            'financial_status': self.financial,
            'order': 'processed_at {}'.format(sorting)
        }

        if self.query:
            if type(self.query) is long:
                params['ids'] = [self.query]
            else:
                params['name'] = self.query

        rep = requests.get(
            url=self.store.get_link('/admin/orders.json', api=True),
            params=params
        )

        rep = rep.json()
        if 'orders' in rep:
            return rep['orders']
        else:
            return []


class ProductsCollectionPaginator(Paginator):
    order = None
    query = None
    extra_filter = None
    ppp = 25

    def set_product_per_page(self, ppp):
        self.ppp = ppp

    def set_current_page(self, page):
        self.current_page = int(page)

    def set_query(self, query):
        self.query = query

    def set_extra_filter(self, extra_filter):
        if len(extra_filter):
            self.extra_filter = extra_filter

    def page(self, number):
        """
        Returns a Page object for the given 1-based page number.
        """

        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page
        if top + self.orphans >= self.count:
            top = self.count

        self.set_current_page(number)

        if self._count > 0 and (not self._products or number != self.current_page):
            self._get_products()

        return self._get_page(self._products, number, self)

    def page_range(self):
        """
        Returns a 1-based range of pages for iterating through within
        a template for loop.
        """
        page_count = self.num_pages

        pages = range(max(1, self.current_page - 5), self.current_page) + range(self.current_page, min(page_count + 1, self.current_page + 5))
        if 1 not in pages:
            pages = [1, None] + pages

        if page_count not in pages:
            pages = pages + [None, page_count]

        return pages

    def _get_products(self):
        rep = self._api_request()
        self._products = rep.get('products', [])

    def _get_product_count(self):
        """
        Returns the total number of objects, across all pages.
        """
        if self._count is None:
            try:
                rep = self._api_request()
                self._count = rep.get('count', 0)
                self._products = rep.get('products')
            except:
                raven_client.captureException()
                self._count = 0

        return self._count

    count = property(_get_product_count)

    def _api_request(self):
        params = {
            'ppp': self.ppp,
            'query': self.query,
            'order': self.order,
            'page': self.current_page,
        }

        if (self.extra_filter):
            params.update(self.extra_filter)

        rep = requests.get(
            url='http://ali-web-api.herokuapp.com/api/products/collections',
            params=params
        )

        return rep.json()
