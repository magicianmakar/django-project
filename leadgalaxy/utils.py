import io
import os
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
import copy

from urllib.parse import urlencode, urlsplit, parse_qs, urlunsplit, urlparse
from hashlib import sha256
from math import ceil

import arrow
import requests
import simplejson as json

from boto.s3.key import Key
from unidecode import unidecode
from collections import Counter

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property
from django.core.paginator import Paginator
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.validators import validate_email, ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404

from raven.contrib.django.raven_compat.models import client as raven_client

from app.celery_base import retry_countdown
from shopified_core import permissions
from shopified_core.utils import (
    safe_int,
    safe_float,
    safe_str,
    list_chunks,
    app_link,
    hash_text,
    random_hash,
    get_domain,
    remove_link_query,
    save_user_ip,
    unique_username,
    send_email_from_template,
    hash_url_filename,
    encode_params,
    http_exception_response,
    extension_hash_text,
    get_top_most_commons,
    get_first_valid_option,
    ensure_title,
)
from leadgalaxy.models import (
    GroupPlan,
    PlanRegistration,
    ShopifyOrderTrack,
    ShopifyBoard,
    ShopifyProduct,
    ShopifyProductImage,
    ShopifyStore,
    ShopifyWebhook,
    UserProfile,
)
from shopified_core.shipping_helper import (
    country_from_code,
    get_uk_province,
    valide_aliexpress_province,
    support_other_in_province,
    fix_br_address
)
from shopify_orders.models import ShopifyOrderLine


def upload_from_url(url, stores=[]):
    # Domains are taken from allowed stores plus store's CDN
    allowed_stores = stores + ['alicdn', 'aliimg', 'ebayimg', 'sunfrogshirts']
    allowed_paths = [r'^https?://s3.amazonaws.com/feather(-client)?-files-aviary-prod-us-east-1/']  # Aviary
    allowed_domains = ['%s.s3.amazonaws.com' % i for i in [settings.S3_STATIC_BUCKET, settings.S3_UPLOADS_BUCKET]]
    allowed_domains += ['cdn.shopify.com', 'cdn2.shopify.com', 'shopifiedapp.s3.amazonaws.com', 'ecx.images-amazon.com',
                        'images-na.ssl-images-amazon.com', 'www.dhresource.com', 'd2kadg5e284yn4.cloudfront.net']

    allowed_mimetypes = ['image/jpeg', 'image/png', 'image/gif']

    can_pull = any([get_domain(url) in allowed_stores,
                    get_domain(url, full=True) in allowed_domains,
                    any([re.search(i, url) for i in allowed_paths])])

    mimetype = mimetypes.guess_type(remove_link_query(url))[0]

    return can_pull and mimetype in allowed_mimetypes


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
        print("REGISTRATIONS SHARED: Change user {} from '{}' to '{}'".format(user.email,
                                                                              profile.plan.title,
                                                                              registration.plan.title))

        if usage['expire_in_days']:
            expire_date = timezone.now() + timezone.timedelta(days=usage['expire_in_days'])

            profile.plan_after_expire = get_plan(plan_hash='606bd8eb8cb148c28c4c022a43f0432d')
            profile.plan_expire_at = expire_date

        profile.plan = registration.plan
        profile.save()

    elif registration.bundle:
        print("REGISTRATIONS SHARED: Add Bundle '{}' to: {} ({})".format(registration.bundle.title,
                                                                         user.username,
                                                                         user.email))

        profile.bundles.add(registration.bundle)

    registration.save()


def create_user_without_signals(**kwargs):
    password = kwargs.get('password')
    if password:
        del kwargs['password']

    user = User(**kwargs)
    user.no_auto_profile = True

    if password:
        user.set_password(password)

    user.save()

    profile = UserProfile.objects.create(user=user)

    return user, profile


def register_new_user(email, fullname, intercom_attributes=None, without_signals=False):
    first_name = ''
    last_name = ''

    if fullname:
        fullname = fullname.title().split(' ')

        if len(fullname):
            first_name = fullname[0]
            last_name = ' '.join(fullname[1:])
    else:
        fullname = []

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
                first_name=first_name[:30],
                last_name=last_name[:30],
                password=password)

        send_email_from_template(
            tpl='register_credentials.html',
            subject='Your Dropified Account',
            recipient=email,
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
                "name": ' '.join(fullname),
                "signed_up_at": arrow.utcnow().timestamp,
                "custom_attributes": {}
            }

            if intercom_attributes.get('phone'):
                data['phone'] = intercom_attributes['phone']
                del intercom_attributes['phone']

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

        user = None
        try:
            user = User.objects.get(email__iexact=email)
        except User.MultipleObjectsReturned:
            user = User.objects.get(email__iexact=email, profile__shopify_app_store=False)

        return user, False


def smart_board_by_product(user, product):
    product_info = {
        'title': product.title,
        'tags': product.tag,
        'type': product.product_type,
    }

    for k, v in list(product_info.items()):
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


def format_data(data, title=True):
    text = ''
    for k, v in list(data.items()):
        t = k
        if title:
            t = t.replace('_', ' ').title()
        text = '{}    {}: {}\n'.format(text, t, v)

    return text


def format_shopify_error(data):
    errors = data['errors']

    if isinstance(errors, str):
        return errors

    msg = []
    for k, v in list(errors.items()):
        if type(v) is list:
            error = ','.join(v)
        else:
            error = v

        if k == 'base':
            msg.append(error)
        else:
            msg.append('{}: {}'.format(k, error))

    return ' | '.join(msg)


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


def verify_shopify_webhook(store, request, throw_excption=True):
    api_data = request.body
    request_hash = request.META.get('HTTP_X_SHOPIFY_HMAC_SHA256')

    webhook_hash = hmac.new(settings.SHOPIFY_API_SECRET.encode(), api_data, sha256).digest()
    webhook_hash = base64.b64encode(webhook_hash).decode()

    if throw_excption:
        assert webhook_hash == request_hash, 'Webhook Verification'

    return webhook_hash == request_hash


def aliexpress_shipping_info(aliexpress_id, country_code):
    shippement_key = 'shipping_info_{}_{}'.format(aliexpress_id, country_code)
    shippement_data = cache.get(shippement_key)

    if shippement_data is not None:
        return shippement_data

    cache_key = 'aliexpress_product_price_{}'.format(aliexpress_id)
    product_price = cache.get(cache_key)

    params = {
        'f': 'd',
        'productid': aliexpress_id,
        'count': '1',
        'currencyCode': 'USD',
        'transactionCurrencyCode': 'USD',
        'sendGoodsCountry': '',
        'country': country_code,
        'province': '',
        'city': '',
        'userType': 'cnfm',
    }

    if product_price:
        params['minPrice'] = product_price
        params['maxPrice'] = product_price

    r = requests.get(url="http://freight.aliexpress.com/ajaxFreightCalculateService.htm", timeout=10, params=params)

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


def ebay_shipping_info(item_id, country_name, zip_code=''):
    from shopified_core.shipping_helper import ebay_country_code

    country_code = ebay_country_code(country_name)
    if not country_code:
        return {}

    shippement_key = 'ebay_shipping_info_{}_{}'.format(item_id, country_code)
    shippement_data = cache.get(shippement_key)

    r = requests.get(
        url="https://shopified-helper-app.herokuapp.com/ebay/shipping/info",
        timeout=10,
        params={
            'product': item_id,
            'country': country_code,
            'zip': zip_code,
        })

    try:
        shippement_data = {
            "freight": r.json()
        }

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
        store = get_object_or_404(stores, id=safe_int(request.GET.get('store')))

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
                return safe_int(re.findall('products/([0-9]+)/variants', url)[0])
            else:
                return safe_int(re.findall('products/([0-9]+)$', url)[0])
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


def get_variant_options(variant):
    variant_options = []
    option_number = 1

    while True:
        option = variant.get('option{}'.format(option_number))
        if option:
            variant_options.append(option)
            option_number += 1
            continue
        break

    return variant_options


def get_image_src(variant, images):
    for image in images:
        if image['id'] == variant['image_id']:
            return image['src']


def update_variants(data, shopify_data):
    data['variants'] = []

    for option in shopify_data['options']:
        data['variants'].append({'title': option['name'], 'values': option['values']})

    return data


def update_variants_images(data, shopify_data):
    images = shopify_data['images']
    data['images'] = [img['src'] for img in images]
    data['variants_images'] = {}
    image_options_map = {}

    for variant in shopify_data['variants']:
        image_src = get_image_src(variant, images)
        if image_src:
            hash_src = hash_url_filename(image_src)
            variant_options = get_variant_options(variant)
            image_options_map.setdefault(hash_src, variant_options).extend(variant_options)
            options = image_options_map.get(hash_src, [])
            most_commons = Counter(options).most_common()
            if most_commons:
                top_most_commons = get_top_most_commons(most_commons)
                if len(top_most_commons) == 1:
                    # Sets the image to its most popular option
                    option, count = top_most_commons[0]
                    data['variants_images'][hash_src] = option
                else:
                    # In case of a tie, assigns the first valid option
                    valid_options = shopify_data['options'][0]['values']
                    data['variants_images'][hash_src] = get_first_valid_option(top_most_commons, valid_options)

    return data


def update_variants_data(product, data):
    shopify_data = get_shopify_product(product.store, product.shopify_id)
    update_variants(data, shopify_data)
    update_variants_images(data, shopify_data)

    return data


def split_product(product, split_factor, store=None):
    data = json.loads(product.data)

    if product.is_connected:
        update_variants_data(product, data)

    new_products = {}

    if data['variants'] and len(data['variants']):
        active_variant = None
        active_variant_idx = None
        for idx, v in enumerate(data['variants']):
            if v['title'] == split_factor:
                active_variant = v
                active_variant_idx = idx + 1

        if active_variant:
            for idx, v in enumerate(active_variant['values']):
                clone = ShopifyProduct.objects.get(id=product.id)
                clone.pk = None
                clone.parent_product = product
                clone.shopify_id = 0

                if product.is_connected:
                    new_data = copy.deepcopy(data)
                else:
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
                new_data['title'] = '{}, {} - {}'.format(data['title'], active_variant['title'], v)

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

                new_products[v] = clone

    return new_products, active_variant_idx


def get_shopify_products_count(store):
    return requests.get(url=store.get_link('/admin/products/count.json', api=True)).json().get('count', 0)


def get_shopify_products(store, page=1, limit=50, all_products=False,
                         product_ids=None, fields=None, session=requests,
                         title=None, product_type=None, status=None, max_products=None, sleep=None):

    if not all_products:
        params = {
            'page': page,
            'limit': limit,
        }

        if product_type:
            params['product_type'] = product_type

        if title:
            params['title'] = title

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

        if status not in ['connected', 'not_connected', 'any']:
            status = None

        pages = int(ceil(count / float(limit)))
        total = 0
        for page in range(1, pages + 1):
            rep = get_shopify_products(store=store, page=page, limit=limit,
                                       title=title, product_type=product_type, fields=fields,
                                       all_products=False, session=requests.session())

            products = {}
            if status:
                for product in ShopifyProduct.objects.filter(store=store).select_related('default_supplier').defer('data'):
                    products[product.shopify_id] = product

            for p in rep:
                if status is None:
                    total += 1
                    yield p
                else:
                    product = products.get(p['id'])
                    if product and product.have_supplier():
                        p['original_url'] = product.default_supplier.product_url
                        p['supplier_name'] = product.default_supplier.get_name()
                        p['status'] = 'connected'
                        p['product'] = product.id
                    else:
                        p['original_url'] = ''
                        p['status'] = 'not_connected'

                    if status == 'any' or status == p['status']:
                        total += 1
                        yield p

            if max_products and total >= max_products:
                break

            if sleep:
                time.sleep(sleep)


def get_shopify_inventories(store, inventory_item_ids, sleep=None):
    if len(inventory_item_ids) <= 50:
        primary_location = store.get_primary_location()
        params = {
            'inventory_item_ids': ','.join(str(x) for x in inventory_item_ids),
            'location_ids': primary_location,
        }

        rep = requests.get(
            url=store.get_link('/admin/inventory_levels.json', api=True),
            params=params
        )

        rep = rep.json()

        for p in rep['inventory_levels']:
            yield p
    else:
        limit = 50
        count = len(inventory_item_ids)

        pages = int(ceil(count / float(limit)))
        for page in range(1, pages + 1):
            start = limit * (page - 1)
            end = limit * page
            rep = get_shopify_inventories(store=store, inventory_item_ids=inventory_item_ids[start:end])

            for p in rep:
                yield p

            if sleep:
                time.sleep(sleep)


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
    product_id = safe_int(product_id)
    variant_id = safe_int(variant_id)
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
                       order_ids=None, fields=None, extra_params={},
                       session=requests, raise_for_status=False, retry=False):

    if not all_orders:
        params = {
            'page': page,
            'limit': limit,
            'status': 'any',
            'order': 'created_at desc'
        }

        params.update(extra_params)

        if order_ids:
            if type(order_ids) is list:
                params['ids'] = ','.join([str(n) for n in order_ids])
            else:
                params['ids'] = order_ids

            ids_count = len(params['ids'].split(','))
            if ids_count > 250:
                for chunk_ids in list_chunks(params['ids'].split(','), 250):
                    for order in get_shopify_orders(store=store, order_ids=chunk_ids, fields=fields, raise_for_status=raise_for_status):
                        yield order

                return

            params['limit'] = ids_count

        if fields:
            if type(fields) is list:
                params['fields'] = ','.join(fields)
            else:
                params['fields'] = fields

        retries = 3 if retry else 1

        while retries > 0:
            rep = session.get(
                url=store.get_link('/admin/orders.json', api=True),
                params=params
            )

            retries -= 1

            if rep.ok:
                break

        if raise_for_status:
            rep.raise_for_status()

        rep = rep.json()

        for p in rep['orders']:
            yield p
    else:
        limit = 250
        count = store.get_orders_count(all_orders=True)

        if not count:
            return

        pages = int(ceil(count / float(limit)))
        for page in range(1, pages + 1):
            rep = get_shopify_orders(store=store, page=page, limit=limit,
                                     fields=fields, all_orders=False,
                                     extra_params=extra_params, session=requests.session(),
                                     raise_for_status=raise_for_status, retry=retry)
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
        note = '{}\n{}'.format(note, new_note)
    else:
        note = new_note

    return set_shopify_order_note(store, order_id, note)


def sync_shopify_products(store, products):
    from leadgalaxy.tasks import update_shopify_product

    product_map = {}
    for i in products:
        if i['qelem'].shopify_id:
            product_map[i['qelem'].shopify_id] = i['qelem']

    if product_map:
        for shopify_product in get_shopify_products(store, limit=100, product_ids=[str(j) for j in list(product_map.keys())]):
            product = product_map[shopify_product['id']]
            if arrow.get(shopify_product['updated_at']).datetime > product.updated_at:
                update_shopify_product.delay(
                    product.store.id,
                    product.shopify_id,
                    shopify_product=shopify_product,
                    product_id=product.id)


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

    for line in order['line_items']:
        if line['product_id'] != product.get_shopify_id():
            continue

        if get_variant(shopify_product, variant_id=line['variant_id']) is None:
            real_id = product.get_real_variant_id(line['variant_id'])
            match = get_variant(shopify_product, variant_title=line['variant_title'])
            if match:
                if real_id != match['id']:
                    product.set_real_variant(line['variant_id'], match['id'])


def shopify_customer_address(order, aliexpress_fix=False, german_umlauts=False, aliexpress_fix_city=False, return_corrections=False):
    if 'shipping_address' not in order \
            and order.get('customer') and order.get('customer').get('default_address'):
        order['shipping_address'] = order['customer'].get('default_address')

    if not order.get('shipping_address'):
        if return_corrections:
            return order, None, {}
        else:
            return order, None

    customer_address = {}
    shipping_address = order['shipping_address']
    for k in list(shipping_address.keys()):
        if shipping_address[k] and type(shipping_address[k]) is str:
            v = re.sub(' ?\xc2?[\xb0\xba] ?', r' ', shipping_address[k])
            if german_umlauts:
                v = re.sub('\u00e4', 'ae', v)
                v = re.sub('\u00c4', 'AE', v)
                v = re.sub('\u00d6', 'OE', v)
                v = re.sub('\u00fc', 'ue', v)
                v = re.sub('\u00dc', 'UE', v)
                v = re.sub('\u00f6', 'oe', v)

            customer_address[k] = unidecode(v)
        else:
            customer_address[k] = shipping_address[k]

    if not customer_address['country']:
        customer_address['country'] = ''

    customer_address['country'] = country_from_code(customer_address['country_code'], customer_address['country'])

    customer_province = customer_address['province']
    if not customer_address['province']:
        if customer_address['country'].lower() == 'united kingdom' and customer_address['city']:
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

    if customer_address['country_code'] == 'FR':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t\._ -]', '', customer_address['zip']).strip().rjust(5, '0')

    if customer_address['country_code'] == 'BR':
        customer_address = fix_br_address(customer_address)

    if customer_address['country_code'] == 'IL':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t\._ -]', '', customer_address['zip']).strip().rjust(7, '0')

    if customer_address['country_code'] == 'CA':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t ]', '', customer_address['zip']).upper().strip()

        if customer_address['province'] == 'Newfoundland':
            customer_address['province'] = 'Newfoundland and Labrador'

    if customer_address['country'].lower() == 'united kingdom':
        if customer_address.get('zip'):
            if not re.findall(r'^([0-9A-Za-z]{2,4}\s[0-9A-Za-z]{3})$', customer_address['zip']):
                customer_address['zip'] = re.sub(r'(.+)([0-9A-Za-z]{3})$', r'\1 \2', customer_address['zip'])

    if customer_address['country_code'] == 'MK':
        customer_address['country'] = 'Macedonia'

    if customer_address['country_code'] == 'PL':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t\._ -]', '', customer_address['zip'])

    customer_address['name'] = ensure_title(customer_address['name'])

    if customer_address['company']:
        customer_address['name'] = '{} - {}'.format(customer_address['name'], customer_address['company'])

    correction = {}
    if aliexpress_fix:
        valide, correction = valide_aliexpress_province(
            customer_address['country'],
            customer_address['province'],
            customer_address['city'],
            auto_correct=True)

        if not valide:
            if support_other_in_province(customer_address['country']):
                customer_address['province'] = 'Other'

                if customer_address['country'].lower() == 'united kingdom' and customer_address['city']:
                    province = get_uk_province(customer_address['city'])
                    if province:
                        customer_address['province'] = province

                if customer_province and customer_address['province'] == 'Other':
                    customer_address['city'] = '{}, {}'.format(customer_address['city'], customer_province)

            elif aliexpress_fix_city:
                city = safe_str(customer_address['city']).strip().strip(',')
                customer_address['city'] = 'Other'

                if not safe_str(customer_address['address2']).strip():
                    customer_address['address2'] = '{},'.format(city)
                else:
                    customer_address['address2'] = '{}, {},'.format(customer_address['address2'].strip().strip(','), city)

        elif correction:
            if 'province' in correction:
                customer_address['province'] = correction['province']

            if 'city' in correction:
                customer_address['city'] = correction['city']

    if return_corrections:
        return order, customer_address, correction
    else:
        return order, customer_address


def shopify_link_images(store, product):
    """
    Link Shopify variants with their images
    """

    mapping = {}
    mapping_idx = {}
    for key, val in enumerate(product['images']):
        var = re.findall('/v-(.+)__', val['src'])

        if len(var) != 1:
            continue

        mapping[var[0]] = val['id']
        mapping_idx[var[0]] = key

    if not len(mapping_idx):
        return None

    for key, val in enumerate(product['variants']):
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
    return hashlib.md5('{}-{}'.format(store_id, settings.SECRET_KEY).encode()).hexdigest()


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

    rep = requests.post(endpoint, json=data)

    try:
        webhook_id = rep.json()['webhook']['id']

        webhook = ShopifyWebhook(store=store, token=token, topic=topic, shopify_id=webhook_id)
        webhook.save()

        return webhook

    except Exception as e:
        raven_client.captureException(extra=http_exception_response(e))
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


def check_webhooks(store):
    endpoint = store.get_link('/admin/webhooks.json', api=True)

    try:
        webhooks = requests.get(endpoint).json()['webhooks']
    except:
        return

    have_http = False
    for hook in webhooks:
        if not hook['address'].startswith('https://'):
            have_http = True
            break

    if have_http:
        raven_client.captureMessage('HTTP Webhook Detected', level='info', tags={'store': store.shop})

        detach_webhooks(store, delete_too=True)
        attach_webhooks(store)


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
                ShopifyOrderTrack.objects.filter(id=tracked.id).update(shopify_status=fulfillment_status)

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
        location_id = kwargs.get('location_id')
        source_tracking = kwargs.get('order_track').source_tracking
        store_id = kwargs.get('order_track').store_id

        if not location_id:
            location_id = kwargs.get('order_track').store.get_primary_location()
    else:
        order_id = kwargs['order_id']
        line_id = kwargs['line_id']
        location_id = kwargs['location_id']
        source_tracking = kwargs['source_tracking']
        store_id = safe_int(kwargs.get('store_id'))

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
            "location_id": location_id,
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
        have_custom_domain = store_id and user_aftership_domain \
            and type(user_aftership_domain) is dict \
            and user_aftership_domain.get(str(store_id))

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
        options = [j for j in [v['option1'], v['option2'], v['option3']] if bool(j)]

        if len(options):
            options = [{'title': j} for j in options]

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
            'var_added': [],
            'var_removed': [],
        }
    }

    if changes and len(changes):
        for change in changes:
            if change.get('level') == 'product':
                remapped['product'][change['name']].append(change)
            if change.get('level') == 'variant':
                remapped['variants'][change['name']].append(change)

    return remapped


def object_dump(obj, desc=None):
    if desc:
        print('object_dump')
        print('===========')
        print(desc, '=', json.dumps(obj, indent=4))
        print('===========')
        print()
    else:
        print(json.dumps(obj, indent=4))


def jvzoo_verify_post(params):
    """Verifies if received POST is a valid JVZoo POST request.

    :param params: POST parameters sent by JVZoo Notification Service
    :type params: dict"""

    if not settings.JVZOO_SECRET_KEY:
        raise Exception('JVZoo secret-key is not set.')

    strparams = ""

    for key in iter(sorted(params.keys())):
        if key in ['cverify', 'secretkey']:
            continue
        strparams += params[key] + "|"
    strparams += settings.JVZOO_SECRET_KEY
    sha = hashlib.sha1(strparams.encode()).hexdigest().upper()
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

    strparams = "{}{}{}{}".format(
        params['seller_id'],
        settings.ZAXAA_API_SIGNATURE,
        params['trans_receipt'],
        params['trans_amount']
    ).upper()

    post_hash = hashlib.md5(strparams.encode()).hexdigest().upper()
    assert params['hash_key'] == post_hash, 'Checksum verification failed. ({} <> {})'.format(params['hash_key'], post_hash)


def zaxaa_parse_post(params):
    """ Parse POST from Zaxaa and extract information we need.

    :param params: POST parameters sent by Zaxaa Notification Service
    :type params: dict """

    return {
        'email': params['cust_email'],
        'fullname': '{} {}'.format(params['cust_firstname'], params['cust_lastname']),
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

    elif 'rover.ebay.com' in url:
        if name != 'mpre':
            ulp = parse_qs(urlparse(url).query)['mpre'].pop()
            ulp = set_url_query(ulp, name, value)

            return set_url_query(url, 'mpre', ulp)
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
        site_id = settings.DROPIFIED_ADMITAD_ID

    return site_id, user_credentials


def get_admitad_affiliate_url(site_id, url):
    api_url = 'https://alitems.com/g/{}/'.format(site_id)

    url = set_url_query(url, '_t', 'coupon.my.feedback.logout')

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

            return None

    except:
        raven_client.captureException(level='warning', extra={'response': rep})

    return None


def get_ebay_affiliate_url(url):
    aff_url = 'http://rover.ebay.com/rover/1/711-53200-19255-0/1?ff3=4&pub=5575259625&toolid=10001&campid=5338443484&customid='

    return affiliate_link_set_query(aff_url, 'mpre', url)


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


def get_shopify_products_filter(request, name=None, default=None):
    if name:
        key = '_shopify_products_filter_{}'.format(name)
        val = request.GET.get(name)

        if not val:
            val = request.user.get_config(key, default)

        return val
    else:
        filters = {}
        for name, val in list(request.user.profile.get_config().items()):
            if name.startswith('_shopify_products_filter_'):
                filters[name.replace('_shopify_products_filter_', '')] = val

        return filters


def set_shopify_products_filter(user, filters, default=None):
    fields = ['category', 'status', 'title']

    for name, val in list(filters.items()):
        if name in fields:
            key = '_shopify_products_filter_{}'.format(name)
            user.set_config(key, val)


def get_orders_filter(request, name=None, default=None, checkbox=False):
    if name:
        key = '_orders_filter_{}'.format(name)
        val = request.GET.get(name)

        if not val:
            val = request.user.get_config(key, default)

        return val
    else:
        filters = {}
        for name, val in list(request.user.profile.get_config().items()):
            if name.startswith('_orders_filter_'):
                filters[name.replace('_orders_filter_', '')] = val

        return filters


def set_orders_filter(user, filters, default=None):
    fields = ['sort', 'status', 'fulfillment', 'financial',
              'desc', 'connected', 'awaiting_order']

    for name, val in list(filters.items()):
        if name in fields:
            key = '_orders_filter_{}'.format(name)
            user.set_config(key, val)


def aws_s3_get_key(filename, bucket_name=None, validate=True):
    if bucket_name is None:
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME

    conn = boto.connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_ACCESS_KEY)
    bucket = conn.get_bucket(bucket_name)

    return bucket.get_key(filename, validate=validate)


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
                gz_out.write(content.encode())

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


def upload_file_to_s3(url, user_id, fp=None):
    # Randomize filename in order to not overwrite an existing file
    name = random_filename(url.split('/')[-1])
    name = 'uploads/u%d/%s' % (user_id, name)
    mimetype = mimetypes.guess_type(url)[0]

    if fp is None:
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux i686; rv:64.0)'
                          ' Gecko/20100101 Firefox/64.0'
        }
        fp = io.BytesIO(requests.get(url, headers=headers).content)

    return aws_s3_upload(
        filename=name,
        fp=fp,
        mimetype=mimetype,
        bucket_name=settings.S3_UPLOADS_BUCKET
    )


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


def update_shopify_product(self, store_id, shopify_id, shopify_product=None, product_id=None):
    try:
        store = ShopifyStore.objects.get(id=store_id)
        try:
            if product_id:
                product = ShopifyProduct.objects.get(store=store, id=product_id)
            else:
                product = ShopifyProduct.objects.get(store=store, shopify_id=shopify_id)
        except:
            return

        if shopify_product is None:
            shopify_product = cache.get('webhook_product_{}_{}'.format(store_id, shopify_id))

        if shopify_product is None:
            rep = requests.get(url=store.get_link('/admin/products/{}.json'.format(shopify_id), api=True))

            if rep.ok:
                shopify_product = rep.json()['product']
            else:
                if rep.status_code in [401, 402, 403, 404]:
                    return
                else:
                    rep.raise_for_status()

        product_data = json.loads(product.data)
        product_data['title'] = shopify_product['title']
        product_data['type'] = shopify_product['product_type']
        product_data['tags'] = shopify_product['tags']
        product_data['images'] = [i['src'] for i in shopify_product['images']]
        product_data['description'] = shopify_product['body_html']
        product_data['published'] = shopify_product.get('published_at') is not None

        prices = [safe_float(i['price'], 0.0) for i in shopify_product['variants']]
        compare_at_prices = [safe_float(i['compare_at_price'], 0.0) for i in shopify_product['variants']]

        if len(set(prices)) == 1:  # If all variants have the same price
            product_data['price'] = prices[0]
            product_data['price_range'] = None
        else:
            product_data['price'] = min(prices)
            product_data['price_range'] = [min(prices), max(prices)]

        if len(set(compare_at_prices)) == 1:  # If all variants have the same compare at price
            product_data['compare_at_price'] = compare_at_prices[0]
        else:
            product_data['compare_at_price'] = max(compare_at_prices)

        product.data = json.dumps(product_data)
        product.save()

        # Delete Product images cache
        ShopifyProductImage.objects.filter(store=store, product=shopify_product['id']).delete()

        # update collections
        ProductCollections().update_product_collects_shopify_id(product)
    except ShopifyStore.DoesNotExist:
        raven_client.captureException()

    except Exception as e:
        raven_client.captureException(level='warning', extra={
            'Store': store.title,
            'Product': shopify_id,
            'Retries': self.request.retries if self else None
        })

        if self and not self.request.called_directly:
            countdown = retry_countdown('retry_product_{}'.format(shopify_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


def fetchall_athena(query_string, output=None):
    import boto3

    client = boto3.client('athena', 'us-east-1')

    query_id = client.start_query_execution(
        QueryString=query_string,
        QueryExecutionContext={
            'Database': 'shopifiedapplogs'
        },
        ResultConfiguration={
            'OutputLocation': 's3://aws-athena-query-results-533310886335-us-east-1'
        }
    )['QueryExecutionId']
    query_status = None
    while query_status == 'QUEUED' or query_status == 'RUNNING' or query_status is None:
        query_status = client.get_query_execution(QueryExecutionId=query_id)['QueryExecution']['Status']['State']
        if query_status == 'FAILED' or query_status == 'CANCELLED':
            raise Exception('Athena query with the string "{}" failed or was cancelled'.format(query_string))

        if output:
            output.write(f'query_status: {query_status}')

        time.sleep(5)

    results_paginator = client.get_paginator('get_query_results')
    results_iter = results_paginator.paginate(
        QueryExecutionId=query_id,
        PaginationConfig={
            'PageSize': 1000
        }
    )
    results = []
    data_list = []
    columns = []

    for results_page in results_iter:
        columns = [
            col['Label']
            for col in results_page['ResultSet']['ResultSetMetadata']['ColumnInfo']
        ]

        for row in results_page['ResultSet']['Rows']:
            data_list.append(row['Data'])

    # names = [x['VarCharValue'] for x in data_list[0]]
    for datum in data_list[1:]:
        results.append([x['VarCharValue'] for x in datum])

    return [dict(zip(columns, x)) for x in results]


def build_query(user, output=None):
    query = 'SELECT * FROM "shopifiedapplogs"."app_logs" WHERE ('
    query += '\n  OR '.join([f"strpos(message,'{ip}') > 0 " for ip in json.loads(user.profile.ips)])
    query += f''') AND '{user.date_joined:%Y-%m-%d}' <= dt
            AND strpos(message, '/api/all/orders-sync?since=') = 0
            AND strpos(message, '/api/can?') = 0
            AND strpos(message, '/api/captcha-credits') = 0
            AND strpos(message, '/api/search-shopify-products-cached') = 0
        ORDER BY generated_at'''

    if output:
        output.write(f'Query:\n{query}\n')

    return query


def generate_user_activity(user, output=None):
    import logfmt

    query = build_query(user, output=output)
    results = fetchall_athena(query, output=output)

    lines = ['\t'.join(["IP", "Time", "HTTP Method", "Path", "Status Code", "Response Bytes"])]
    for i in results:
        try:
            message = re.sub(r'hmac=[A-Za-z0-9]+', 'hmac=secret', i['message'])
            message = list(logfmt.parse(io.StringIO(message)))[0]
            date = arrow.get(i['generated_at']).datetime
            lines.append('\t'.join([
                message['fwd'].split(',')[0],
                f"{date:%d/%b/%Y:%H:%M:%S %z}",
                message['method'],
                f'"https://app.dropified.com{message["path"]}"',
                message['status'],
                message['bytes']
            ]))
        except:
            if output:
                output.write('Ignore line...')

    email_filename = re.sub(r"[@\.]", "_", user.email)

    url = aws_s3_upload(
        filename=f'activity/logs-{email_filename}.csv',
        content='\n'.join(lines),
        bucket_name='aws-athena-query-results-533310886335-us-east-1',
    )

    return url


# Helper Classes
class TimezoneMiddleware(object):

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tzname = request.session.get('django_timezone')
        if not tzname:
            if request.user.is_authenticated:
                tzname = request.user.profile.timezone
                request.session['django_timezone'] = request.user.profile.timezone

        if tzname:
            timezone.activate(pytz.timezone(tzname))
        else:
            timezone.deactivate()

        return self.get_response(request)


class UserIpSaverMiddleware(object):

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.session.get('is_hijacked_user'):
            save_user_ip(request)

        return self.get_response(request)


class UserEmailEncodeMiddleware(object):

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'GET':
            if request.GET.get('f') and request.GET.get('title'):
                if self.need_encoding(request, 'title'):
                    return self.encode_param(request, 'title')

            if request.path == '/orders':
                for p in ['query_order', 'query', 'query_customer']:
                    if request.GET.get(p) and self.need_encoding(request, p):
                        return self.encode_param(request, p)

        return self.get_response(request)

    def need_encoding(self, request, name):
        value = request.GET.get(name)

        if '@' in value:
            try:
                validate_email(value)
                return True

            except ValidationError:
                pass

        return False

    def encode_param(self, request, name, value=None):
        if value is None:
            value = request.GET.get(name) or ''

        params = request.GET.copy()
        params[name] = encode_params(value)

        return HttpResponseRedirect('{}?{}'.format(request.path, params.urlencode()))


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

        pages = list(range(max(1, self.current_page - 5), self.current_page))
        pages.extend(list(range(self.current_page, min(page_count + 1, self.current_page + 5))))

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
    ppp = settings.ITEMS_PER_PAGE

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

        pages = list(range(max(1, self.current_page - 5), self.current_page))
        pages.extend(list(range(self.current_page, min(page_count + 1, self.current_page + 5))))

        if 1 not in pages:
            pages = [1, None] + pages

        if page_count not in pages:
            pages = pages + [None, page_count]

        return pages

    def _get_products(self):
        rep = self._api_request()
        self._products = rep.get('products', [])

    @cached_property
    def count(self):
        """
        Returns the total number of objects, across all pages.
        """
        try:
            rep = self._api_request()
            self._count = rep.get('count', 0)
            self._products = rep.get('products')
        except:
            raven_client.captureException()
            self._products = []
            self._count = 0

        return self._count

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

    def mark_as_ordered_note(self, line_id, source_id, track=None):
        source = 'Aliexpress'

        if track:
            url = track.get_source_url()
            if track.source_type == 'ebay':
                source = 'eBay'
        else:
            url = 'http://trade.aliexpress.com/order_detail.htm?orderId={}'.format(source_id)

        note = '{} Order ID: {}\n{}'.format(source, source_id, url)

        if line_id:
            note = '{}\nOrder Line: #{}'.format(note, line_id)

        self.add_note(note)

    def mark_as_ordered_attribute(self, source_id, track=None):
        source = 'Aliexpress'

        if track:
            url = track.get_source_url()
            if track.source_type == 'ebay':
                source = 'eBay'
        else:
            url = 'http://trade.aliexpress.com/order_detail.htm?orderId={}'.format(source_id)

        name = '{} Order #{}'.format(source, source_id)

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
            new_note = '\n'.join([i for i in self.notes if i not in current_note])

            order_data = {
                'order': {
                    'id': int(self.order_id),
                    'note': '{}\n{}'.format(current_note, new_note).strip()[:5000]
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

    def have_changes(self):
        return any([self.notes, self.attributes, self.tags])

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

        if len(list(order_data.keys())) > 1:
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

    def get_collections(self, store, title=''):
        params = {'limit': 100}
        if title:
            params['title'] = title

        try:
            response = requests.get(url=store.get_link(self.shopify_api_urls.get('custom_collections'), api=True), params=params).json()
            collections = [{'title': collection.get('title'), 'id': collection.get('id')} for collection in
                           response.get('custom_collections', [])]
        except:
            raven_client.captureException()
            collections = []

        return collections

    def link_product_collection(self, product, collections):
        collections = list(map(int, collections))
        response = requests.get(
            url=product.store.get_link(self.shopify_api_urls.get('product_collections').format(product.shopify_id), api=True)
        ).json()

        self.unlink_product_collection(product=product, collections=[
            {'id': collect.get('id'), 'collection_id': collect.get('collection_id')} for collect in
            response.get('collects', [])], selected=collections)

        for collection in collections:
            if collection not in [collect.get('collection_id') for collect in response.get('collects', [])]:
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
        selected = list(map(int, selected))
        for collection in collections:
            if collection['collection_id'] not in selected:
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
