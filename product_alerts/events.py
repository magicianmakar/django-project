import simplejson as json
import requests

from django.core.cache import cache
from django.template.defaultfilters import truncatewords

from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.utils import send_email_from_template
from shopify_revision.models import ProductRevision
from leadgalaxy.utils import get_variant_name


class ProductChangeEvent():

    def __init__(self, product_change):
        self.revision = ProductRevision(
            store=product_change.product.store,
            product=product_change.product,
            product_change=product_change,
            shopify_id=product_change.product.get_shopify_id()
        )
        self.save_revision = False
        self.notify_events = []
        self.base_product_url = 'https://app.dropified.com/product'

        events = json.loads(product_change.data)
        self.product_changes = events['changes']['product']
        if 'variants' in events['changes']:
            self.variants_changes = events['changes']['variants']
        else:
            self.variants_changes = []

        self.product = product_change.product
        self.user = product_change.user

        self.variants_map = self.product.get_variant_mapping()
        if not len(self.variants_map.keys()):
            self.variants_map = None

        self.config = {
            'product_disappears': self.get_config('alert_product_disappears'),
            'variant_disappears': self.get_config('alert_variant_disappears'),
            'quantity_change': self.get_config('alert_quantity_change'),
            'price_change': self.get_config('alert_price_change'),
        }

    def get_config(self, name, default='notify'):
        value = self.product.get_config().get(name)
        if value is None:
            value = self.user.get_config(name, default)

        return value

    def prepare_data_before(self, data):
        # Remember original price in case it changes
        for variant in data['product']['variants']:
            variant['_original_price'] = variant['price']

        return data

    def prepare_data_after(self, data):
        # Remove new key original_price before sending to shopify
        for variant in data['product']['variants']:
            del variant['_original_price']

        return data

    def take_action(self):
        data = self.get_shopify_product()
        # emails will be queued and sent as batch via management command with cron on regular basis. e.g. 24 hrs
        # self.notify(data)

        self.revision.data = data

        if data is not None:
            data = self.prepare_data_before(data)
            data = self.product_actions(data)
            data = self.variants_actions(data)

            if self.save_revision:
                self.revision.save()

                data = self.prepare_data_after(data)
                self.send_shopify(data)

    def send_email(self, product_data):
        image = product_data['product'].get('image')
        if image and type(image) is dict:
            image = image.get('src')

        data = {
            'username': self.user.username,
            'email': self.user.email,
            'events': self.notify_events,
            'product_title': self.product.title,
            'product_image': image,
            'shopify_link': self.product.store.get_link('/admin/products/{}'.format(
                self.product.get_shopify_id())),
            'store_title': self.product.store.title,
            'store_link': self.product.store.get_link()
        }

        html_message = send_email_from_template(
            'product_change_notify.html',
            '[Dropified] AliExpress Product Alert',
            self.user.email,
            data,
            nl2br=False
        )

        cache.set('last_product_change_email', html_message, timeout=3600)

    def notify(self, product_data):
        notify_key = 'product_change_%d' % self.user.id
        if cache.get(notify_key):
            # We already sent the user a notification for a product change
            return

        product_name = truncatewords(self.product.get_product(), 5)

        for product_change in self.product_changes:
            if product_change['category'] == 'Vendor' and self.config['product_disappears'] == 'notify':
                availability = "Online" if not product_change['new_value'] else "Offline"
                self.notify_events.append(
                    u'Product <a href="{}/{}">{}</a> is {}.'.format(
                        self.base_product_url, self.product.id, product_name, availability))

        for variant in self.variants_changes:
            variant_name = get_variant_name(variant)
            for change in variant['changes']:
                if self.config['variant_disappears'] == 'notify' and change['category'] == 'removed':
                    self.notify_events.append(
                        u'Variant <a href="{}/{}">{}</a> were removed.'.format(
                            self.base_product_url, self.product.id, variant_name))

                elif self.config['price_change'] == 'notify' and change['category'] == 'Price':
                    self.notify_events.append(
                        u'Variants <a href="{}/{}">{}</a> has its Price changed from ${:,.2f} to ${:,.2f}.'.format(
                            self.base_product_url, self.product.id, variant_name, change['old_value'], change['new_value']))

                elif self.config['quantity_change'] == 'notify' and change['category'] == 'Availability':
                    self.notify_events.append(
                        u'Variants <a href="{}/{}">{}</a> has its Availability changed from {} to {}.'.format(
                            self.base_product_url, self.product.id, variant_name, change['old_value'], change['new_value']))

        self.notify_events = list(set(self.notify_events))
        if len(self.notify_events):
            # Disable notification for a day
            cache.set(notify_key, True, timeout=86400)
            self.send_email(product_data)

    def get_previous_product_revision(self, event_name, new_value):
        found_revision = None
        for revision in ProductRevision.objects.select_related('product_change').filter(product_id=self.product.id):
            change_data = json.loads(revision.product_change.data)
            for product_change in change_data['changes']['product']:
                if product_change['category'] == event_name and product_change['new_value'] == new_value:
                    found_revision = revision
                    break
            if found_revision is not None:
                break
        return found_revision

    def get_shopify_product(self):
        """ Get product from shopify using link from ShopifyStore Model """

        cache_key = 'alert_product_{}'.format(self.product.id)
        shopify_product = cache.get(cache_key)
        if shopify_product is not None:
            cache.delete(cache_key)
            return {'product': shopify_product}

        url = self.product.store.get_link('/admin/products/{}.json'.format(
            self.product.get_shopify_id()), api=True)
        response = requests.get(url)

        response.raise_for_status()
        return response.json()

    def send_shopify(self, data):
        update_endpoint = self.product.store.get_link('/admin/products/{}.json'.format(
            self.product.get_shopify_id()), api=True)
        try:
            response = requests.put(update_endpoint, json=data)
            response.raise_for_status()
        except Exception as e:
            raven_client.captureException(extra={
                'response': e.response.text if hasattr(e, 'response') and e.response else ''
            })

    def product_actions(self, data):
        for product_change in self.product_changes:
            if product_change['category'] == 'Vendor':
                if self.config['product_disappears'] == 'unpublish':
                    data['product']['published'] = not product_change['new_value']
                    self.save_revision = True

                elif self.config['product_disappears'] == 'zero_quantity':
                    if product_change['new_value'] is True:
                        for idx, variant in enumerate(data['product']['variants']):
                            data['product']['variants'][idx]['inventory_quantity'] = 0
                            data['product']['variants'][idx]['inventory_management'] = 'shopify'
                            data['product']['variants'][idx]['inventory_policy'] = 'deny'
                            self.save_revision = True
                    else:
                        # Try to find variants from previous revision
                        revision = self.get_previous_product_revision('Vendor', True)
                        revision_variants = []
                        if revision is not None:
                            revision_variants = json.loads(revision.data)['product']['variants']

                        for idx, variant in enumerate(data['product']['variants']):
                            # look for previous revision variant or use old_inventory_quantity
                            inventory = variant['old_inventory_quantity']
                            for revision_variant in revision_variants:
                                if revision_variant['id'] == variant['id']:
                                    inventory = revision_variant['inventory_quantity']
                                    break

                            data['product']['variants'][idx]['inventory_quantity'] = inventory
                            data['product']['variants'][idx]['inventory_management'] = 'shopify'
                            data['product']['variants'][idx]['inventory_policy'] = 'deny'
                            self.save_revision = True
        return data

    def get_found_variant(self, variant, data):
        # try to find the alerted variants
        found = []
        search = get_variant_name(variant).split(' / ')

        if search:
            if self.variants_map is not None:
                found_map = []
                for key, variant in self.variants_map.items():
                    if not isinstance(variant, basestring):
                        variant = str(variant)

                    match = [x for x in search if x.lower() in variant.lower()]
                    if len(match) == len(search):
                        found_map.append(key)

                for key, variant in enumerate(data['product']['variants']):
                    if str(variant['id']) in found_map:
                        found.append(key)
            else:
                for key, variant in enumerate(data['product']['variants']):
                    match = [x for x in search if x.lower() in variant['title'].lower()]
                    if len(match) == len(search):
                        found.append(key)

        return found

    def variants_actions(self, data):
        for variant in self.variants_changes:
            found_variants = self.get_found_variant(variant, data)

            for change in variant['changes']:
                if len(found_variants) > 0:
                    if change['category'] == 'removed':
                        # take proper action with the found variant
                        if self.config['variant_disappears'] == 'remove':
                            for found in found_variants[::-1]:
                                del data['product']['variants'][found]
                                self.save_revision = True

                        elif self.config['variant_disappears'] == 'zero_quantity':
                            for found in found_variants:
                                data['product']['variants'][found]['inventory_quantity'] = 0
                                data['product']['variants'][found]['inventory_management'] = 'shopify'
                                data['product']['variants'][found]['inventory_policy'] = 'deny'
                                self.save_revision = True

                    elif change['category'] == 'Price':
                        # take proper action with the found variant
                        if self.config['price_change'] == 'update' or (self.config['price_change'] == 'update_for_increase' and
                                                                       change['new_value'] > change['old_value']):
                            for found in found_variants:
                                data['product']['variants'][found]['price'] = data['product']['variants'][found]['_original_price']
                                selling_price = float(data['product']['variants'][found]['price'])
                                old_price = change['old_value']
                                data['product']['variants'][found]['price'] = change['new_value'] + (selling_price - old_price)
                                self.save_revision = True

                    elif change['category'] == 'Availability':
                        if self.config['quantity_change'] == 'update':
                            for found in found_variants:
                                data['product']['variants'][found]['inventory_quantity'] = change['new_value']
                                data['product']['variants'][found]['inventory_management'] = 'shopify'
                                data['product']['variants'][found]['inventory_policy'] = 'deny'
                                self.save_revision = True
        return data
