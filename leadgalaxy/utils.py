import json
import requests
import uuid
import md5

from django.core.mail import send_mail
from leadgalaxy.models import *

from app import settings


def safeInt(v, default=0.0):
    try:
        return int(v)
    except:
        return default


def safeFloat(v, default=0.0):
    try:
        return float(v)
    except:
        return default


def random_hash():
    token = str(uuid.uuid4())
    return md5.new(token).hexdigest()


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
        token = md5.new(token).hexdigest()

        access_token = AccessToken(user=user, token=token)
        access_token.save()

    return access_token.token


def get_user_from_token(token):
    try:
        access_token = AccessToken.objects.get(token=token)
    except:
        return None

    if len(token) and access_token:
        return access_token.user

    return None


def generate_plan_registration(plan, data={}):
    reg = PlanRegistration(plan=plan, data=json.dumps(data))
    reg.register_hash = random_hash()
    reg.save()

    return reg


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


def format_data(data):
    text = ''
    for k, v in data.items():
        text = '{}    {}: {}\n'.format(text, k.replace('_', ' ').title(), v)

    return text


def slack_invite(data):
    success = False
    rep = ''
    try:
        r = requests.post(
                url='https://shopifiedapp.slack.com/api/users.admin.invite',
                data={
                    'email': data['email'],
                    'first_name': data['firstname'],
                    'last_name': data['lastname'],
                    'channels': 'C0F23PPE2,C0FA60BC6,C0FA6GYHM,C0F1M7X8R,C0FA6RYKW',
                    'token': 'xoxp-15055768838-15056514242-19294251986-f79c8c24f4',
                    'set_active': True,
                    '_attempts': 1
                }
        )

        success = r.json()['ok']
        rep = r.text
    except Exception as e:
        rep = str(e)

    if not success:
        send_mail(subject='Slack Invite Fail',
                  recipient_list=['chase@rankengine.com', 'ma7dev@gmail.com'],
                  from_email='chase@rankengine.com',
                  message='Slack Invite was not sent to {} due the following error:\n{}'.format(data['email'], rep))


def get_myshopify_link(user, default_store, link):
    stores = [default_store, ]
    for i in user.shopifystore_set.all():
        if i not in stores:
            stores.append(i)

    for store in stores:
        handle = link.split('/')[-1]

        r = requests.get(store.get_link('/admin/products.json', api=True), params={'handle': handle}).json()
        if len(r['products']) == 1:
            return store.get_link('/admin/products/{}'.format(r['products'][0]['id']))

    return None


def get_shopify_product(store, product_id):
    rep = requests.get(url=store.get_link('/admin/products/{}.json'.format(product_id), api=True)).json()
    return rep.get('product')


def get_shopify_variant_image(store, product_id, variant_id):
    """ product_id: Product ID in Shopify """
    product_id = safeInt(product_id)
    variant_id = safeInt(variant_id)
    image = None

    try:
        cached = ShopifyProductImage.objects.get(store=store, product=product_id, variant=variant_id)
        return cached.image
    except:
        pass

    if variant_id:
        variant = requests.get(store.get_link('/admin/variants/{}.json'.format(variant_id), api=True)).json()

    try:
        image_id = variant['variant']['image_id']
        image = requests.get(
            store.get_link('/admin/products/{}/images/{}.json'.format(product_id, image_id), api=True)).json()
        image = image['image']['src']
    except:
        product = requests.get(store.get_link('/admin/products/{}.json'.format(product_id), api=True)).json()
        image = product['product']['image']['src']

    if image:
        cached = ShopifyProductImage(store=store, product=product_id, variant=variant_id, image=image)
        cached.save()

        return image
    else:
        return None


def get_shopify_order(store, order_id):
    rep = requests.get(store.get_link('/admin/orders/{}.json'.format(order_id), api=True)).json()
    return rep['order']


def get_shopify_order_line(store, order_id, line_id):
    order = get_shopify_order(store, order_id)
    for line in order['line_items']:
        if int(line['id']) == int(line_id):
            return line

    return False


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


def add_shopify_order_note(store, order_id, new_note):
    note = get_shopify_order_note(store, order_id)

    if note:
        note = '{}\n{}'.format(note, new_note)
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

            option = option.replace(' ', '_')
            img_idx = mapping_idx.get(option)

            if not img_idx:
                continue

            if val['id'] not in product['images'][img_idx]['variant_ids']:
                product['images'][img_idx]['variant_ids'].append(val['id'])

    return requests.put(
        url=store.get_link('/admin/products/{}.json'.format(product['id']), api=True),
        json={'product': product}
    )


def webhook_token(store_id):
    return md5.new('{}-{}'.format(store.id, settings.SECRET_KEY)).hexdigest()


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

    rep = requests.post(endpoint, json=data)

    webhook_id = 0
    try:
        webhook_id = rep.json()['webhook']['id']
    except:
        print 'WEBHOOK:', rep.text

    if not webhook_id:
        return None

    webhook = ShopifyWebhook(store=store, token=token, topic=topic, shopify_id=webhook_id)
    webhook.save()

    return webhook


def attach_webhooks(store):
    print 'WEBHOOK: attach_webhooks', store
    default_topics = ['products/update']

    for topic in default_topics:
        create_shopify_webhook(store, topic)


def detach_webhooks(store, delete_too=False):
    print 'WEBHOOK: detach_webhooks', store, delete_too
    for webhook in store.shopifywebhook_set.all():
        webhook.detach()

        if delete_too:
            webhook.delete()


def get_tracking_orders(store, tracker_orders):
    ids = []
    for i in tracker_orders:
        ids.append(str(i.order_id))

    params = {
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
            lines['{}-{}'.format(order['id'], line['id'])] = line

    new_tracker_orders = []
    for tracked in tracker_orders:
        tracked.order = orders[tracked.order_id]
        tracked.line = lines['{}-{}'.format(tracked.order_id, tracked.line_id)]
        new_tracker_orders.append(tracked)

    return new_tracker_orders
