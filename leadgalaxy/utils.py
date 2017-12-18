import os
import simplejson as json
import requests
import hashlib
import pytz
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
import urlparse
from urllib import urlencode
from hashlib import sha256
from math import ceil

from tld import get_tld
from boto.s3.key import Key
from unidecode import unidecode

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
from shopified_core.utils import (
    app_link,
    save_user_ip,
    unique_username,
    send_email_from_template,
    hash_url_filename,
    extension_hash_text
)

from shopified_core.shipping_helper import get_uk_province, valide_aliexpress_province
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

    hostname = urlparse.urlparse(url).hostname
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


def get_plan(plan_hash=None, plan_slug=None, payment_gateway=None):
    try:
        assert plan_hash != plan_slug

        plan = GroupPlan.objects

        if payment_gateway:
            plan = plan.filter(payment_gateway=payment_gateway)

        if plan_hash:
            return plan.get(register_hash=plan_hash)
        else:
            return plan.get(slug=plan_slug)
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


def create_user_without_signals(**kwargs):
    post_save.disconnect(userprofile_creation, User, dispatch_uid="userprofile_creation")

    password = kwargs.get('password')
    if password:
        del kwargs['password']

    user = User(**kwargs)

    if password:
        user.set_password(password)

    user.save()

    profile = UserProfile.objects.create(user=user)

    post_save.connect(userprofile_creation, User, dispatch_uid="userprofile_creation")

    return user, profile


def register_new_user(email, fullname, intercom_attributes=None, without_signals=False):
    first_name = ''
    last_name = ''

    if fullname:
        fullname = fullname.title().split(' ')

        if len(fullname):
            first_name = fullname[0]
            last_name = u' '.join(fullname[1:])

    username = unique_username(email, fullname=fullname)
    password = get_random_string(12)

    if not User.objects.filter(email__iexact=email).exists():
        if not without_signals:
            user = User.objects.create(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name)

            user.set_password(password)
            user.save()

        else:
            user, profile = create_user_without_signals(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password)

        send_email_from_template(
            tpl='register_credentials.html',
            subject='Your Dropified Account',
            recipient=email,
            nl2br=False,
            data={
                'user': user,
                'password': password
            },
        )

        if settings.INTERCOM_ACCESS_TOKEN:
            headers = {
                'Authorization': 'Bearer {}'.format(settings.INTERCOM_ACCESS_TOKEN),
                'Accept': 'application/json'
            }

            data = {
                "user_id": user.id,
                "email": user.email,
                "name": u' '.join(fullname),
                "signed_up_at": arrow.utcnow().timestamp,
                "custom_attributes": {}
            }

            try:
                data['custom_attributes'].update({
                    'plan': user.profile.plan.title
                })
            except:
                pass

            if intercom_attributes:
                data['custom_attributes'].update(intercom_attributes)

            try:
                requests.post('https://api.intercom.io/users', headers=headers, json=data).text
            except:
                raven_client.captureException()

        return user, True

    else:
        raven_client.captureMessage('New User Registration Exists', extra={
            'name': fullname,
            'email': email,
            'count': User.objects.filter(email__iexact=email).count()
        })

        return User.objects.get(email__iexact=email), False


def smart_board_by_product(user, product):
    product_info = {
        'title': product.title,
        'tags': product.tag,
        'type': product.product_type,
    }

    for k, v in product_info.items():
        if v:
            product_info[k] = [i.lower().strip() for i in v.split(',')]
        else:
            product_info[k] = []

    for i in user.shopifyboard_set.all():
        try:
            config = json.loads(i.config)
        except:
            continue

        product_added = False
        for j in ['title', 'tags', 'type']:
            if product_added:
                break

            if not len(config.get(j, '')) or not product_info[j]:
                continue

            for f in config.get(j, '').split(','):
                if f.lower() and f.lower().strip() in product_info[j]:
                    i.products.add(product)
                    product_added = True

                    break

        if product_added:
            i.save()


def smart_board_by_board(user, board):
    for product in user.shopifyproduct_set.only('id', 'title', 'product_type', 'tag').all()[:1000]:
        product_info = {
            'title': product.title,
            'tags': product.tag,
            'type': product.product_type,
        }

        for k, v in product_info.items():
            if v:
                product_info[k] = [i.lower().strip() for i in v.split(',')]
            else:
                product_info[k] = []

        try:
            config = json.loads(board.config)
        except:
            continue

        product_added = False
        for j in ['title', 'tags', 'type']:
            if product_added:
                break

            if not len(config.get(j, '')) or not product_info[j]:
                continue

            for f in config.get(j, '').split(','):
                if f.lower().strip() in product_info[j]:
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


def wicked_report_add_user(request, user):
    try:

        from shopified_core.shipping_helper import country_from_code

        if not settings.WICKED_REPORTS_API:
            return

        user_ip = request.META['HTTP_X_REAL_IP']

        ipinfo = requests.get(
            url='http://ipinfo.io/{}'.format(user_ip),
            timeout=3
        )

        ipinfo = ipinfo.json() if ipinfo.ok else {}

        data = {
            'SourceSystem': 'ActiveCampaign',
            'SourceID': user.id,
            'CreateDate': arrow.get(user.date_joined).format("YYYY-MM-DD HH:mm:ss"),
            'Email': user.email,
            'FirstName': (user.first_name or '').encode('utf-8'),
            'LastName': (user.last_name or '').encode('utf-8'),
            'City': ipinfo.get('city'),
            'State': ipinfo.get('region'),
            'Country': country_from_code(ipinfo.get('country'), default=''),
            'IP_Address': user_ip,
        }

        rep = requests.post(
            url='https://api.wickedreports.com/contacts',
            headers={'apikey': settings.WICKED_REPORTS_API},
            json=data,
            timeout=3
        )

        rep.raise_for_status()

        if not user.profile.country and ipinfo.get('country'):
            user.profile.country = ipinfo.get('country')
            user.profile.save()

    except Exception as e:
        response = ''
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            response = e.response.text

        raven_client.captureException(
            level='warning',
            extra={'response': response}
        )


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

    product_data = json.loads(product.data)

    if parent_product.shopify_id and parent_product.store:
        try:
            shopify_product = get_shopify_product(parent_product.store, parent_product.shopify_id, raise_for_status=True)

            product_data['variants'] = []

            for option in shopify_product['options']:
                product_data['variants'].append({
                    'values': option['values'],
                    'title': option['name']
                })

            product_data['variants_sku'] = {}
            product_data['variants_images'] = {}
            for variant in shopify_product['variants']:
                if len(variant['sku']) > 0:
                    titles = variant['title'].split(' / ')
                    values = variant['sku'].split(';')
                    if titles:
                        if values:
                            product_data['variants_sku'][titles[0]] = variant['sku']
                        else:
                            for k, v in titles:
                                if values.length > k:
                                    product_data['variants_sku'][titles[k]] = values[k]
                    else:
                        product_data['variants_sku'][variant['title']] = variant['sku']

                for image in shopify_product['images']:
                    if image['id'] == variant['image_id']:
                        product_data['variants_images'][variant['title']] = image['src']

            product.data = json.dumps(product_data)

        except Exception:
            raven_client.captureException(level='warning')

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

                suppliers = product.productsupplier_set.all()
                for i in suppliers:
                    i.pk = None
                    i.product = clone
                    i.store = clone.store
                    i.save()

                    if i.is_default or len(suppliers) == 1:
                        clone.set_default_supplier(i, commit=True)

                if not clone.have_supplier() and len(suppliers):
                    clone.set_default_supplier(suppliers[0], commit=True)

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


def get_shopify_orders(store, page=1, limit=50, all_orders=False,
                       order_ids=None, fields=None, session=requests):

    if not all_orders:
        params = {
            'page': page,
            'limit': limit,
            'status': 'any',
            'order': 'created_at desc'
        }

        if order_ids:
            if type(order_ids) is list:
                params['ids'] = ','.join(order_ids)
            else:
                params['ids'] = order_ids

        if fields:
            if type(fields) is list:
                params['fields'] = ','.join(fields)
            else:
                params['fields'] = fields

        rep = session.get(
            url=store.get_link('/admin/orders.json', api=True),
            params=params
        )

        rep = rep.json()

        for p in rep['orders']:
            yield p
    else:
        limit = 250
        count = store.get_orders_count(all_orders=True)

        if not count:
            return

        pages = int(ceil(count / float(limit)))
        for page in xrange(1, pages + 1):
            rep = get_shopify_orders(store=store, page=page, limit=limit,
                                     fields=fields, all_orders=False, session=requests.session())
            for p in rep:
                yield p


def get_shopify_order_line(store, order_id, line_id, line_sku=None, note=False, shopify_data=None):
    if shopify_data is None:
        order = get_shopify_order(store, order_id)
    else:
        order = shopify_data

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


def fix_order_variants(store, order, product):
    product_key = 'fix_product_{}_{}'.format(store.id, product.get_shopify_id())
    shopify_product = cache.get(product_key)

    if shopify_product is None:
        shopify_product = get_shopify_product(store, product.get_shopify_id())
        cache.set(product_key, shopify_product)

    def normalize_name(n):
        return n.lower().replace(' and ', '').replace(' or ', '').replace(' ', '')

    def get_variant(product, variant_id=None, variant_title=None):
        for v in product['variants']:
            if variant_id and v['id'] == int(variant_id):
                return v
            elif variant_title and normalize_name(v['title']) == normalize_name(variant_title):
                return v

        return None

    def set_real_variant(product, deleted_id, real_id):
        config = product.get_config()
        mapping = config.get('real_variant_map', {})
        mapping[str(deleted_id)] = int(real_id)

        config['real_variant_map'] = mapping

        product.config = json.dumps(config, indent=4)
        product.save()

    for line in order['line_items']:
        if line['product_id'] != product.get_shopify_id():
            continue

        if get_variant(shopify_product, variant_id=line['variant_id']) is None:
            real_id = product.get_real_variant_id(line['variant_id'])
            match = get_variant(shopify_product, variant_title=line['variant_title'])
            if match:
                if real_id != match['id']:
                    set_real_variant(product, line['variant_id'], match['id'])


def shopify_customer_address(order, aliexpress_fix=False, german_umlauts=False):
    if 'shipping_address' not in order \
            and order.get('customer') and order.get('customer').get('default_address'):
        order['shipping_address'] = order['customer'].get('default_address')

    if not order.get('shipping_address'):
        return order, None

    customer_address = {}
    shipping_address = order['shipping_address']
    for k in shipping_address.keys():
        if shipping_address[k] and type(shipping_address[k]) is unicode:
            v = re.sub('\xc2\xb0 ?'.decode('utf-8'), r' ', shipping_address[k])
            if german_umlauts:
                v = re.sub(u'\u00e4', 'ae', v)
                v = re.sub(u'\u00c4', 'AE', v)
                v = re.sub(u'\u00d6', 'OE', v)
                v = re.sub(u'\u00fc', 'ue', v)
                v = re.sub(u'\u00dc', 'UE', v)
                v = re.sub(u'\u00f6', 'oe', v)

            customer_address[k] = unidecode(v)
        else:
            customer_address[k] = shipping_address[k]

    customer_province = customer_address['province']
    if not customer_address['province']:
        if customer_address['country'] == 'United Kingdom' and customer_address['city']:
            province = get_uk_province(customer_address['city'])
            customer_address['province'] = province
        else:
            customer_address['province'] = customer_address['country_code']

    elif customer_address['province'] == 'Washington DC':
        customer_address['province'] = 'Washington'

    elif customer_address['province'] == 'Puerto Rico':
        # Puerto Rico is a country in Aliexpress
        customer_address['province'] = 'PR'
        customer_address['country_code'] = 'PR'
        customer_address['country'] = 'Puerto Rico'

    elif customer_address['province'] == 'Virgin Islands':
        # Virgin Islands is a country in Aliexpress
        customer_address['province'] = 'VI'
        customer_address['country_code'] = 'VI'
        customer_address['country'] = 'Virgin Islands (U.S.)'

    elif customer_address['province'] == 'Guam':
        # Guam is a country in Aliexpress
        customer_address['province'] = 'GU'
        customer_address['country_code'] = 'GU'
        customer_address['country'] = 'Guam'

    if customer_address['country_code'] == 'CA':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t ]', '', customer_address['zip']).upper().strip()

        if customer_address['province'] == 'Newfoundland':
            customer_address['province'] = 'Newfoundland and Labrador'

    if customer_address['country'] == 'United Kingdom':
        if customer_address.get('zip'):
            if not re.findall('^([0-9A-Za-z]{2,4}\s[0-9A-Za-z]{3})$', customer_address['zip']):
                customer_address['zip'] = re.sub(r'(.+)([0-9A-Za-z]{3})$', r'\1 \2', customer_address['zip'])

    if customer_address['country_code'] == 'MK':
        customer_address['country'] = 'Macedonia'

    customer_address['name'] = ensure_title(customer_address['name'])

    if customer_address['company']:
        customer_address['name'] = u'{} - {}'.format(customer_address['name'], customer_address['company'])

    if aliexpress_fix:
        if not valide_aliexpress_province(customer_address['country'], customer_address['province'], customer_address['city']):
            customer_address['province'] = 'Other'

            if customer_address['country'] == 'United Kingdom' and customer_address['city']:
                province = get_uk_province(customer_address['city'])
                if province:
                    customer_address['province'] = province

            if customer_province and customer_address['province'] == 'Other':
                customer_address['city'] = u'{}, {}'.format(customer_address['city'], customer_province)

    return order, customer_address


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
        for option_title in [val['option1'], val['option2'], val['option3']]:
            if not option_title:
                continue

            option = re.sub('[^A-Za-z0-9 _-]', '', option_title)
            option = re.sub(' +', '_', option)

            img_idx = mapping_idx.get(option)

            if not img_idx:
                img_idx = mapping_idx.get(str(extension_hash_text(option)))

            if not img_idx:
                img_idx = mapping_idx.get(str(extension_hash_text(option_title)))

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


def update_shopify_product_vendor(store, product_shopify_id, vendor):
    api_product = {
        'id': product_shopify_id,
        'vendor': vendor
    }
    return requests.put(
        url=store.get_link('/admin/products/{}.json'.format(product_shopify_id), api=True),
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
            'address': app_link('webhook', 'shopify', topic.replace('/', '-'), store=store.id, t=token)
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
    carrier = shipping_carrier(tarcking_number)
    if not tarcking_number or (re.match('^[0-9]+$', tarcking_number) and (not carrier or (carrier and 'TNT' in carrier))):
        return False
    else:
        return True


def is_chinese_carrier(tarcking_number):
    return tarcking_number and re.search('(CN|SG|HK)$', tarcking_number) is not None


def shipping_carrier(tracking_number, all_matches=False):
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
        'pattern': "^(\\d{12}$)|^(\\d{15}$)|^(96\\d{20}$)|^(7489\\d{16}$)|^(6129\\d{16}$)"
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

    matches = []
    for p in patterns:
        if p['pattern'] and re.search(p['pattern'], tracking_number):
            matches.append(p['name'])

    if len(matches):
        return matches if all_matches else matches[0]

    return None


def is_shipping_carrier(tracking_number, carrier, any_match=False):
    carriers = shipping_carrier(tracking_number, all_matches=any_match)
    if not carriers:
        return False

    if any_match:
        for i in carriers:
            if i.lower() == carrier.lower():
                return True
    else:
        if carriers.lower() == carrier.lower():
            return True

    return False


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
    tracking_numbers = None

    if source_tracking and ',' in source_tracking.strip(','):
        tracking_numbers = source_tracking.split(',')
        source_tracking = tracking_numbers[0]

    try:
        if kwargs.get('use_usps') is None:  # Find line when shipping method is not selected
            line = ShopifyOrderLine.objects.select_related('order').get(
                line_id=line_id,
                order__store_id=store_id,
                order__order_id=order_id)

            is_usps = (is_chinese_carrier(source_tracking) or shipping_carrier(source_tracking) == 'USPS') \
                and line.order.country_code == 'US' \
                and not is_shipping_carrier(source_tracking, 'FedEx', any_match=True)

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
        if tracking_numbers:
            data['fulfillment']['tracking_numbers'] = tracking_numbers
            del data['fulfillment']['tracking_number']
        else:
            data['fulfillment']['tracking_number'] = source_tracking

        user_aftership_domain = user_config.get('aftership_domain')
        have_custom_domain = store_id and user_aftership_domain and type(user_aftership_domain) is dict

        if (kwargs.get('use_usps') is None and is_usps and not have_custom_domain) or kwargs.get('use_usps'):
            data['fulfillment']['tracking_company'] = user_config.get('_default_shipping_carrier', 'USPS')
        elif (kwargs.get('use_usps') is None and not have_custom_domain) and is_shipping_carrier(source_tracking, 'FedEx', any_match=True):
            data['fulfillment']['tracking_company'] = "FedEx"
        else:
            aftership_domain = 'http://track.aftership.com/{{tracking_number}}'

            if have_custom_domain:
                aftership_domain = user_aftership_domain.get(str(store_id), aftership_domain)
                if '{{tracking_number}}' not in aftership_domain:
                    aftership_domain = "http://{}.aftership.com/{{{{tracking_number}}}}".format(aftership_domain)
                elif not aftership_domain.startswith('http'):
                    aftership_domain = 'http://{}'.format(re.sub('^([:/]*)', r'', aftership_domain))

            data['fulfillment']['tracking_company'] = "Other"
            if tracking_numbers:
                data['fulfillment']['tracking_urls'] = [aftership_domain.replace('{{tracking_number}}', i) for i in tracking_numbers]
            else:
                data['fulfillment']['tracking_url'] = aftership_domain.replace('{{tracking_number}}', source_tracking)

    if user_config.get('validate_tracking_number', False) \
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

    if kwargs.get('return_line'):
        return data, line
    else:
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

    scheme, netloc, path, query_string, fragment = urlparse.urlsplit(url)
    query_params = urlparse.parse_qs(query_string)
    query_params[param_name] = [param_value]
    new_query_string = urlencode(query_params, doseq=True)
    return urlparse.urlunsplit((scheme, netloc, path, new_query_string, fragment))


def affiliate_link_set_query(url, name, value):
    if '/deep_link.htm' in url:
        dl_target_url = urlparse.parse_qs(urlparse.urlparse(url).query)['dl_target_url'].pop()
        dl_target_url = set_url_query(dl_target_url, name, value)

        return set_url_query(url, 'dl_target_url', dl_target_url)
    elif 'alitems.com' in url:
        if name != 'ulp':
            ulp = urlparse.parse_qs(urlparse.urlparse(url).query)['ulp'].pop()
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


def attach_boards_with_product(user, product, ids):
    # remove boards
    boards = ShopifyBoard.objects.filter(products=product).exclude(id__in=ids)
    for board in boards:
        board.products.remove(product)
        board.save()

    # attach new boards
    boards = ShopifyBoard.objects.filter(id__in=ids)
    if boards:
        for board in boards:
            permissions.user_can_edit(user, board)
            board.products.add(product)
            board.save()


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


class UserIpSaverMiddleware(object):

    def process_request(self, request):
        if request.user.is_authenticated() and not request.session.get('is_hijacked_user'):
            save_user_ip(request)


class ShopifyOrderPaginator(Paginator):
    reverse_order = False
    query = None

    def set_store(self, store):
        self.store = store

    def set_filter(self, status, fulfillment, financial, created_at_start=None, created_at_end=None):
        self.status = status
        self.fulfillment = fulfillment
        self.financial = financial
        self.created_at_start = created_at_start
        self.created_at_end = created_at_end

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

        if self.created_at_start:
            params['created_at_min'] = self.created_at_start

        if self.created_at_end:
            params['created_at_max'] = self.created_at_end

        if self.query:
            params['ids'] = self.query

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


class ShopifyOrderUpdater:

    def __init__(self, store=None, order_id=None):
        self.store = store
        self.order_id = order_id

        self.notes = []
        self.tags = []
        self.attributes = []

    def add_note(self, n):
        self.notes.append(n)

    def add_tag(self, t):
        if type(t) is not list:
            t = t.split(',')

        for i in t:
            self.tags.append(i)

    def add_attribute(self, a):
        if type(a) is not list:
            a = [a]

        for i in a:
            self.attributes.append(i)

    def mark_as_ordered_note(self, line_id, source_id):
        note = 'Aliexpress Order ID: {0}\n' \
               'http://trade.aliexpress.com/order_detail.htm?orderId={0}'.format(source_id)

        if line_id:
            note = u'{}\nOrder Line: #{}'.format(note, line_id)

        self.add_note(note)

    def mark_as_ordered_attribute(self, source_id):
        name = u'Aliexpress Order #{}'.format(source_id)
        url = u'http://trade.aliexpress.com/order_detail.htm?orderId={0}'.format(source_id)
        note_attribute = {'name': name, 'value': url}

        self.add_attribute(note_attribute)

    def mark_as_ordered_tag(self, source_id):
        self.add_tag(str(source_id))

    def save_changes(self):
        with cache.lock('updater_lock_{}_{}'.format(self.store.id, self.order_id), timeout=15):
            self._do_save_changes()

    def _do_save_changes(self):
        order = get_shopify_order(self.store, self.order_id)

        if self.notes:
            current_note = order.get('note', '') or ''
            new_note = '\n'.join(self.notes)

            order_data = {
                'order': {
                    'id': int(self.order_id),
                    'note': '{}\n{}'.format(current_note.encode('utf-8'), new_note.encode('utf-8')).strip()[:500]
                }
            }

            rep = requests.put(
                url=self.store.get_link('/admin/orders/{}.json'.format(self.order_id), api=True),
                json=order_data
            )

            rep.raise_for_status()

        if self.tags:
            new_tags = [i.strip() for i in order.get('tags', '').split(',')]
            for i in self.tags:
                new_tags.append(i)

            new_tags = ','.join(new_tags)

            order_data = {
                'order': {
                    'id': int(self.order_id),
                    'tags': new_tags[:5000].strip(', ')
                }
            }

            rep = requests.put(
                url=self.store.get_link('/admin/orders/{}.json'.format(self.order_id), api=True),
                json=order_data
            )

            rep.raise_for_status()

            time.sleep(1)

        if self.attributes:
            new_attributes = order.get('note_attributes', [])
            for i in self.attributes:
                new_attributes.append(i)

            order_data = {
                'order': {
                    'id': int(self.order_id),
                    'note_attributes': new_attributes
                }
            }

            rep = requests.put(
                url=self.store.get_link('/admin/orders/{}.json'.format(self.order_id), api=True),
                json=order_data
            )

            rep.raise_for_status()

            time.sleep(1)

    def delay_save(self, countdown=None):
        from leadgalaxy.tasks import order_save_changes

        order_save_changes.apply_async(
            args=[self.toJSON()],
            countdown=countdown
        )

    def reset(self, what):
        order_data = {
            'id': int(self.order_id),
        }

        if 'notes' in what:
            order_data['note'] = ''

        if 'tags' in what:
            order_data['tags'] = ''

        if 'attributes' in what:
            order_data['note_attributes'] = []

        if len(order_data.keys()) > 1:
            rep = requests.put(
                url=self.store.get_link('/admin/orders/{}.json'.format(self.order_id), api=True),
                json={'order': order_data}
            )

            rep.raise_for_status()

    def toJSON(self):
        return json.dumps({
            "attributes": self.attributes,
            "notes": self.notes,
            "order": self.order_id,
            "store": self.store.id,
            "tags": self.tags
        }, sort_keys=True, indent=4)

    def fromJSON(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        self.store = ShopifyStore.objects.get(id=data.get("store"))
        self.order_id = data.get("order")

        self.notes = data.get("notes")
        self.tags = data.get("tags")
        self.attributes = data.get("attributes")


class ProductCollections(object):
    shopify_api_urls = {
        'custom_collections': '/admin/custom_collections.json',
        'collection_products': '/admin/collects.json?collection_id={}',
        'product_collections': '/admin/collects.json?product_id={}',
        'link_collection': '/admin/collects.json',
        'unlink_collection': '/admin/collects/{}.json',
    }

    def get_collections(self, store):
        try:
            response = requests.get(url=store.get_link(self.shopify_api_urls.get('custom_collections'), api=True)).json()
            collections = [{'title': collection.get('title'), 'id': collection.get('id')} for collection in
                           response.get('custom_collections', [])]
        except:
            raven_client.captureException()
            collections = []

        return collections

    def link_product_collection(self, product, collections):
        response = requests.get(
            url=product.store.get_link(self.shopify_api_urls.get('product_collections').format(product.shopify_id), api=True)
        ).json()

        self.unlink_product_collection(product=product, collections=[
            {'id': collection.get('id'), 'collection_id': collection.get('collection_id')} for collection in
            response.get('collects', [])], selected=collections)

        for collection in collections:
            if collection not in [collection.get('collection_id') for collection in response.get('collects', [])]:
                requests.post(
                    product.store.get_link(self.shopify_api_urls.get('link_collection'), api=True),
                    json={
                        'collect': {
                            'product_id': product.shopify_id,
                            'collection_id': collection
                        }
                    }).json()

        # update already linked collections
        self.update_product_collects_shopify_id(product)

    def unlink_product_collection(self, product, collections, selected):
        for collection in collections:
            if str(collection['collection_id']) not in selected:
                requests.delete(product.store.get_link(
                    self.shopify_api_urls.get('unlink_collection').format(collection['id']),
                    api=True))

    def update_product_collects_shopify_id(self, product):
        # check if we have any unlinked product collection
        try:
            url = product.store.get_link(self.shopify_api_urls.get('product_collections').format(product.shopify_id), api=True)
            response = requests.get(url=url).json()
            data = json.loads(product.data)
            data['collections'] = [collection.get('collection_id') for collection in response.get('collects', [])]
            product.data = json.dumps(data)
            product.save()

        except:
            raven_client.captureException()
