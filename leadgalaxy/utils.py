import os
import simplejson as json
import requests
import uuid
import hashlib
import pytz
import collections
import time
from urlparse import urlparse
import xml.etree.ElementTree as ET

from django.core.mail import send_mail
from django.template import Context, Template
from django.utils import timezone
from django.utils.html import strip_tags
from django.core.paginator import Paginator
from django.core.cache import cache

from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.models import *
from shopify_orders.models import ShopifyOrder, ShopifyOrderLine

from app import settings


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


def get_domain(url):
    if not url:
        return None

    hostname = urlparse(url).hostname
    if hostname is None:
        return hostname

    for i in ['com', 'co.uk', 'org', 'net']:
        hostname = hostname.replace('.%s' % i, '')

    return hostname.split('.')[-1]


def random_hash():
    token = str(uuid.uuid4())
    return hashlib.md5(token).hexdigest()


def hash_text(text):
    return hashlib.md5(text).hexdigest()

def create_new_profile(user):
    plan = GroupPlan.objects.filter(default_plan=1).first()
    profile = UserProfile(user=user, plan=plan)
    profile.save()

    return profile


def get_access_token(user):
    try:
        access_token = AccessToken.objects.filter(user=user).latest('created_at')
    except:
        token = str(uuid.uuid4())
        token = hashlib.md5(token).hexdigest()

        access_token = AccessToken(user=user, token=token)
        access_token.save()

    return access_token.token


def get_user_from_token(token):
    if not token:
        return None

    try:
        access_token = AccessToken.objects.get(token=token)
    except AccessToken.DoesNotExist:
        return None
    except:
        raven_client.captureException()
        return None

    if len(token) and access_token:
        return access_token.user

    return None


def login_attempts_exceeded(username):
    from django.core.cache import cache

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


def verify_shopify_webhook(store, request):
    import hmac
    import base64
    from hashlib import sha256

    api_secret = store.get_api_credintals().get('api_secret')
    webhook_hash = hmac.new(api_secret.encode(), request.body, sha256).digest()
    webhook_hash = base64.encodestring(webhook_hash).strip()

    assert webhook_hash == request.META.get('X-Shopify-Hmac-Sha256'), 'Webhook Verification'


def slack_invite(data, team='users'):
    slack_teams = {
        'users': {
            'token': 'xoxp-21001000400-20999486737-21000357922-4047773e5d',
            'channels': ['C0M6TTRAM', 'C0VN18AGP', 'C0LVBD3FD', 'C0V9EKPLG', 'C0V9P89S6',
                         'C0M6V41S4', 'C10RT5BFC', 'C0V7P4TTM'],
        },
        'ecom': {
            'token': 'xoxp-25785177045-25785177061-28041998548-c6763c7a78',
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
    r = requests.get(url="http://freight.aliexpress.com/ajaxFreightCalculateService.htm?",
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
    except:
        shippement_data = {}

    return shippement_data


def get_myshopify_link(user, default_store, link):
    stores = [default_store, ]
    for i in user.profile.get_active_stores():
        if i not in stores:
            stores.append(i)

    for store in stores:
        handle = link.split('/')[-1]

        r = requests.get(store.get_link('/admin/products.json', api=True), params={'handle': handle}).json()
        if len(r['products']) == 1:
            return store.get_link('/admin/products/{}'.format(r['products'][0]['id']))

    return None


def get_shopify_products_count(store):
    return requests.get(url=store.get_link('/admin/products/count.json', api=True)).json().get('count', 0)


def get_shopify_products(store, page=1, limit=50, all_products=False, session=requests):
    if not all_products:
        rep = session.get(
            url=store.get_link('/admin/products.json', api=True),
            params={
                'page': page,
                'limit': limit
            }
        ).json()

        for p in rep['products']:
            yield p
    else:
        from math import ceil

        limit = 200
        count = get_shopify_products_count(store)

        if not count:
            return

        pages = int(ceil(count/float(limit)))
        for page in xrange(1, pages+1):
            rep = get_shopify_products(store=store, page=page, limit=limit,
                                       all_products=False, session=requests.session())
            for p in rep:
                yield p


def get_shopify_product(store, product_id):
    rep = requests.get(url=store.get_link('/admin/products/{}.json'.format(product_id), api=True)).json()
    return rep.get('product')


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
    rep = requests.get(store.get_link('/admin/orders/{}.json'.format(order_id), api=True)).json()
    return rep['order']


def get_shopify_order_line(store, order_id, line_id, note=False):
    order = get_shopify_order(store, order_id)
    for line in order['line_items']:
        if int(line['id']) == int(line_id):
            if note:
                line, order['note']
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
                    'note': note
                }
            }
    ).json()

    return rep['order']['id']


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
        rep = requests.post(endpoint, json=data).json()
        webhook_id = rep['webhook']['id']

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
    default_topics = ['products/update', 'products/delete', 'orders/updated', 'orders/delete']

    webhooks = []
    for topic in default_topics:
        webhook = get_shopify_webhook(store, topic)

        if not webhook:
            webhook = create_shopify_webhook(store, topic)

        if webhook:
            webhooks.append(webhook)

    return webhooks


def detach_webhooks(store, delete_too=False):
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
        new_tracker_orders.append(tracked)

    return new_tracker_orders


def is_valide_tracking_number(tarcking_number):
    return tarcking_number and re.match('^[0-9]+$', tarcking_number) is None


def is_chinese_carrier(tarcking_number):
    return tarcking_number and re.search('(CN|SG|HK)$', tarcking_number) is not None


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

    try:
        line = ShopifyOrderLine.objects.get(line_id=line_id, order__order_id=order_id)
        is_usps = is_chinese_carrier(source_tracking) and line.order.country_code == 'US'

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
        if is_usps or kwargs.get('use_usps'):
            data['fulfillment']['tracking_company'] = "USPS"
        else:
            aftership_domain = 'track'

            if store_id and type(user_config.get('aftership_domain')) is dict:
                aftership_domain = user_config.get('aftership_domain').get(str(store_id), aftership_domain)

            data['fulfillment']['tracking_company'] = "Other"
            data['fulfillment']['tracking_url'] = "https://{}.aftership.com/{}".format(aftership_domain,
                                                                                       source_tracking)

    if user_config.get('validate_tracking_number', True) and \
            not is_valide_tracking_number(source_tracking):
        notify_customer = 'no'
    else:
        notify_customer = user_config.get('send_shipping_confirmation', 'default')

    if notify_customer and notify_customer != 'default':
        data['fulfillment']['notify_customer'] = (notify_customer == 'yes')

    return data


def product_change_notify(user):

    notify_key = 'product_change_%d' % user.id
    if user.get_config('_product_change_notify') or cache.get(notify_key):
        # We already sent the user a notification for a product change
        return

    template_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'emails', 'product_change_notify.html')
    template = Template(open(template_file).read())

    data = {
        'username': user.username,
        'email': user.email,
    }

    ctx = Context(data)

    email_html = template.render(ctx)
    email_html = email_html.replace('\n', '<br />')

    send_mail(subject='[Shopified App] AliExpress Product Alert',
              recipient_list=[data['email']],
              from_email='no-reply@shopifiedapp.com',
              message=email_html,
              html_message=email_html)

    user.set_config('_product_change_notify', True)

    # Disable notification for a day
    cache.set(notify_key, True, timeout=86400)


def get_variant_name(variant):
    options = re.findall('#([^;:]+)', variant.get('variant_desc', ''))
    if len(options):
        return ' / '.join([i.title() for i in options])
    else:
        name = variant.get('variant_id')
        return name if name else '<Default>'


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


def calc_orders_limit(orders_count, check_freq=30, total_time=1440, min_count=20):
    """
    Calculate Orders update check limit

    orders_count: Total number of orders
    check_freq: Extension check interval (minutes)
    total_time: Total time amount to verify all orders (minutes)
    min_count: Minimum orders check limit
    """

    limit = (orders_count * check_freq) / total_time

    return max(limit, min_count)


def object_dump(obj, desc=None):
    if desc:
        print 'object_dump'
        print '==========='
        print desc, '=', json.dumps(obj, indent=4)
        print '==========='
        print
    else:
        print json.dumps(obj, indent=4)


def jvzoo_verify_post(params, secretkey):
    """Verifies if received POST is a valid JVZoo POST request.

    :param params: POST parameters sent by JVZoo Notification Service
    :type params: dict"""

    if not secretkey:
        raise Exception('JVZoo secret-key is not set.')

    strparams = u""

    for key in iter(sorted(params.iterkeys())):
        if key in ['cverify', 'secretkey']:
            continue
        strparams += params[key] + "|"
    strparams += secretkey
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


def get_aliexpress_promotion_links(appkey, trackingID, urls, fields='publisherId,trackingId,promotionUrls'):
    try:
        r = requests.get(
            url='http://gw.api.alibaba.com/openapi/param2/2/portals.open/api.getPromotionLinks/{}'.format(appkey),
            params={
                'fields': fields,
                'trackingId': trackingID,
                'urls': urls

            }
        )

        r = r.json()
        errorCode = r['errorCode']
        if errorCode != 20010000:
            raven_client.captureMessage('Aliexpress Promotion Error',
                                        extra={'errorCode': errorCode},
                                        level='warning')
            return None

        if len(r['result']['promotionUrls']):
            return r['result']['promotionUrls'][0]['promotionUrl']
        else:
            return None

    except:
        raven_client.captureException(level='warning')

    return None


def get_user_affiliate(user):
    api_key, tracking_id = user.get_config(['aliexpress_affiliate_key',
                                            'aliexpress_affiliate_tracking'])

    if not user.can('aliexpress_affiliate.use') or not api_key or not tracking_id:
        api_key, tracking_id = ['37954', 'shopifiedapp']

    return api_key, tracking_id


def send_email_from_template(tpl, subject, recipient, data, nl2br=True):
        template_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'emails', tpl)
        template = Template(open(template_file).read())

        ctx = Context(data)

        email_html = template.render(ctx)

        if nl2br:
            email_html = email_html.replace('\n', '<br />')

        if type(recipient) is not list:
            recipient = [recipient]

        send_mail(subject=subject,
                  recipient_list=recipient,
                  from_email='support@shopifiedapp.com',
                  message=email_html,
                  html_message=email_html)


def get_countries():
    country_names = pytz.country_names
    country_names = collections.OrderedDict(sorted(country_names.items(), key=lambda i: i[1]))
    countries = zip(country_names.keys(), country_names.values())

    return countries


def get_timezones(country=None):
    import datetime
    import re

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
              'desc', 'connected']

    for name, val in filters.items():
        if name in fields:
            key = '_orders_filter_{}'.format(name)
            user.set_config(key, val)


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


class ProductFeed():
    feed = None
    domain = 'uncommonnow.com'
    currency = 'USD'

    def __init__(self, store, revision=1):
        self.store = store
        self.info = store.get_info

        self.currency = self.info['currency']
        self.domain = self.info['domain']

        self.revision = safeInt(revision, 1)

    def _add_element(self, parent, tag, text):
        element = ET.SubElement(parent, tag)
        element.text = text

        return element

    def init(self):
        self.root = ET.Element("rss")
        self.root.attrib['xmlns:g'] = 'http://base.google.com/ns/1.0'
        self.root.attrib['version'] = '2.0'

        self.channel = ET.SubElement(self.root, 'channel')

        self._add_element(self.channel, 'title', self.info['name'])
        self._add_element(self.channel, 'link', 'https://{}'.format(self.info['domain']))
        self._add_element(self.channel, 'description', '{} Products Feed'.format(self.info['name']))

    def add_product(self, product):
        if len(product['variants']):
            for variant in product['variants']:
                self._add_variant(product, variant)

    def _add_variant(self, product, variant):
        image = product.get('image')
        if image:
            image = image.get('src')
        else:
            return None

        item = ET.SubElement(self.channel, 'item')

        if self.revision == 1:
            self._add_element(item, 'g:id', 'store_{p[id]}_{v[id]}'.format(p=product, v=variant))
        else:
            self._add_element(item, 'g:id', '{}'.format(variant['id']))

        self._add_element(item, 'g:link', 'https://{domain}/products/{p[handle]}?variant={v[id]}'.format(domain=self.domain, p=product, v=variant))
        self._add_element(item, 'g:title', product.get('title'))
        self._add_element(item, 'g:description', self._clean_description(product))
        self._add_element(item, 'g:image_link', image)
        self._add_element(item, 'g:price', '{amount} {currency}'.format(amount=variant.get('price'), currency=self.currency))
        self._add_element(item, 'g:shipping_weight', '{variant[weight]} {variant[weight_unit]}'.format(variant=variant))
        self._add_element(item, 'g:brand', product.get('vendor'))
        self._add_element(item, 'g:google_product_category', product.get('product_type'))
        self._add_element(item, 'g:availability', 'in stock')
        self._add_element(item, 'g:condition', 'new')

        return item

    def _clean_description(self, product):
        text = product.get('body_html', '')
        text = re.sub('<br */?>', '\n', text)
        text = strip_tags(text).strip()

        if len(text) == 0:
            text = product.get('title', '')

        return text

    def get_feed_stream(self):
        yield u'<?xml version="1.0" encoding="utf-8"?>'

        for i in ET.tostringlist(self.root, encoding='utf-8', method="xml"):
            yield i

    def get_feed(self, formated=False):
        xml = ET.tostring(self.root, encoding='utf-8', method="xml")

        if formated:
            return self.prettify(xml)
        else:
            return u'{}\n{}'.format(u'<?xml version="1.0" encoding="utf-8"?>', xml.decode('utf-8'))

    def prettify(self, xml_str):
        """Return a pretty-printed XML string for the Element.
        """
        from xml.dom import minidom

        reparsed = minidom.parseString(xml_str)
        return reparsed.toprettyxml(indent="  ")

    def save(self, filename):
        tree = ET.ElementTree(self.root)
        tree.write(filename, encoding='utf-8', xml_declaration=True)


class SimplePaginator(Paginator):
    current_page = 0

    def page(self, number):
        self.current_page = number
        return super(SimplePaginator, self).page(number)

    def page_range(self):
        """
        Returns a 1-based range of pages for iterating through within
        a template for loop.
        """
        page_count = self.num_pages

        pages = range(max(1, self.current_page-5), self.current_page) + range(self.current_page, min(page_count + 1, self.current_page+5))
        if 1 not in pages:
            pages = [1, None] + pages

        if page_count not in pages:
            pages = pages + [None, page_count]

        return pages


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

        pages = range(max(1, self.current_page-5), self.current_page)+range(self.current_page, min(page_count + 1, self.current_page+5))
        if 1 not in pages:
            pages = [1, None] + pages

        if page_count not in pages:
            pages = pages + [None, page_count]

        return pages

    def get_orders(self, page):
        if self.reverse_order:
            order = 'asc'
        else:
            order = 'desc'

        if self.query and type(self.query) is long:
            rep = requests.get(
                url=self.store.get_link('/admin/orders/{}.json'.format(self.query), api=True),
                params={
                    'limit': self.order_limit,
                    'page': page,
                    'status': self.status,
                    'fulfillment_status': self.fulfillment,
                    'financial_status': self.financial,
                    'order': 'processed_at '+order
                }
            )
            rep = rep.json()
            if 'order' in rep:
                return [rep['order']]
            else:
                return []

        else:
            params = {
                'limit': self.order_limit,
                'page': page,
                'status': self.status,
                'fulfillment_status': self.fulfillment,
                'financial_status': self.financial,
                'order': 'processed_at '+order
            }

            if self.query:
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

        pages = range(max(1, self.current_page-5), self.current_page)+range(self.current_page, min(page_count + 1, self.current_page+5))
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
