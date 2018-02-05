import simplejson as json
import requests

from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.utils import app_link
from leadgalaxy.utils import get_shopify_product
from product_alerts.utils import variant_index
from product_alerts.models import ProductVariantPriceHistory


class ProductChangeManager():
    @classmethod
    def initialize(cls, product_change):
        manager = None
        if product_change.store_type == 'shopify':
            manager = ShopifyProductChangeManager(product_change)
        elif product_change.store_type == 'chq':
            manager = CommerceHQProductChangeManager(product_change)
        return manager

    def __init__(self, product_change):
        self.product_change = product_change
        changes = json.loads(product_change.data)
        self.product_changes = []
        self.variant_changes = []
        for change in changes:
            if change.get('level') == 'product':
                self.product_changes.append(change)
            elif change.get('level') == 'variant':
                self.variant_changes.append(change)

        self.product = product_change.product
        self.user = product_change.user

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

    def need_update(self):
        """ Return True if the user have any setting that will require a product update """

        for k, v in self.config.items():
            if v not in ['notify', 'none']:
                return True

        return False

    def apply_changes(self):
        try:
            if not self.need_update():
                # No need to check for updates, the user doesn't have any setting that will require a product update
                self.product_change.status = 1  # Applied
                self.product_change.save()
                return

            product_data = self.get_product_data()

            if product_data:
                product_change_data = self.apply_product_changes(product_data)
                if product_change_data:  # Do we have any change on the product level?
                    product_data = product_change_data

            if product_data:
                product_data = self.apply_variant_changes(product_data)

            if product_data:
                self.update_product(product_data)

            self.product_change.status = 1  # Applied
            self.product_change.save()

            return product_data

        except Exception:
            self.product_change.status = 2  # Failed
            self.product_change.save()

        return None

    def get_product_data(self):
        pass

    def apply_product_changes(self, product_data):
        if self.product_changes:
            for product_change in self.product_changes:
                if product_change.get('name') == 'offline':
                    if product_change.get('new_value') and not product_change.get('old_value'):  # disappeared
                        product_data = self.handle_product_disappear(product_data)
                    elif product_change.get('old_value') and not product_change.get('new_value'):  # appeared
                        product_data = self.handle_product_appear(product_data)

        return product_data

    def apply_variant_changes(self, product_data):
        if self.variant_changes:
            for variant_change in self.variant_changes:
                if variant_change.get('name') == 'price':
                    product_data = self.handle_variant_price_change(product_data, variant_change)
                elif variant_change.get('name') == 'quantity':
                    product_data = self.handle_variant_quantity_change(product_data, variant_change)
                elif variant_change.get('name') == 'var_added':
                    product_data = self.handle_variant_added(product_data, variant_change)
                elif variant_change.get('name') == 'var_removed':
                    product_data = self.handle_variant_removed(product_data, variant_change)

        return product_data

    def handle_product_disappear(self, product_data):
        return product_data

    def handle_product_appear(self, product_data):
        return product_data

    def get_variant(self, product_data, variant_change):
        # 14:173#66Blue;5:361386 <OptionGroup>:<OptionID>#<OptionTitle>;
        sku = variant_change.get('sku')
        return variant_index(self.product, sku, product_data['variants'])

    def handle_variant_price_change(self, product_data, variant_change):
        idx = self.get_variant(product_data, variant_change)
        if idx is not None:
            variant_id = product_data['variants'][idx]['id']
            self.add_price_history(variant_id, variant_change)

        if self.config['price_change'] == 'notify':
            return None
        elif self.config['price_change'] == 'update':
            if idx is not None:
                product_data['variants'][idx]['price'] = variant_change.get('new_value')
        elif self.config['price_change'] == 'update_for_increase':
            if idx is not None and product_data['variants'][idx]['price'] < variant_change.get('new_value'):
                product_data['variants'][idx]['price'] = variant_change.get('new_value')

        return product_data

    def handle_variant_quantity_change(self, product_data, variant_change):
        return product_data

    def handle_variant_added(self, product_data, variant_change):
        return product_data

    def handle_variant_removed(self, product_data, variant_change):
        return product_data

    def update_product(self, product_data):
        pass

    def changes_map(self):
        changes_map = {
            'availability': [],
            'price': [],
            'quantity': [],
            'removed': [],
            'added': [],
        }
        if self.product_change.store_type == 'shopify':
            common_data = {
                'images': self.product.get_images(),
                'title': self.product.title,
                'url': app_link('product', self.product.id),
                'target_url': self.product.store.get_link('/admin/products/{}'.format(self.product.get_shopify_id())),
                'open_orders': self.product_change.orders_count()
            }
        if self.product_change.store_type == 'chq':
            common_data = {
                'images': [self.product.get_image()],
                'title': self.product.title,
                'url': app_link('chq/product', self.product.id),
                'target_url': self.product.commercehq_url,
                'open_orders': self.product_change.orders_count()
            }
        if self.product_changes:
            for product_change in self.product_changes:
                if product_change.get('name') == 'offline' and self.config['product_disappears'] == 'notify':
                    changes_map['availability'].append(dict({
                        'from': 'Offline' if product_change.get('old_value') else 'Online',
                        'to': 'Offline' if product_change.get('new_value') else 'Online',
                    }, **common_data))

        if self.variant_changes:
            new_prices = []
            old_prices = []
            new_quantities = []
            old_quantities = []
            added_variants = []
            removed_variants = []
            for variant_change in self.variant_changes:
                if variant_change.get('name') == 'price':
                    new_prices.append(variant_change['new_value'])
                    old_prices.append(variant_change['old_value'])
                if variant_change.get('name') == 'quantity':
                    new_quantities.append(variant_change['new_value'])
                    old_quantities.append(variant_change['old_value'])
                if variant_change.get('name') == 'var_added':
                    added_variants.append(variant_change['sku'])
                if variant_change.get('name') == 'var_removed':
                    removed_variants.append(variant_change['sku'])
            if self.config['variant_disappears'] == 'notify' and len(removed_variants):
                changes_map['removed'].append(dict({
                    'variants': removed_variants
                }, **common_data))
            if self.config['variant_disappears'] == 'notify' and len(added_variants):
                changes_map['added'].append(dict({
                    'variants': added_variants
                }, **common_data))
            if self.config['price_change'] == 'notify':
                new_prices = list(set(new_prices))
                old_prices = list(set(old_prices))
                if len(new_prices):
                    from_range = '${:.02f} - ${:.02f}'.format(min(old_prices), max(old_prices))
                    to_range = '${:.02f} - ${:.02f}'.format(min(new_prices), max(new_prices))

                    changes_map['price'].append(dict({
                        'from': '${:.02f}'.format(old_prices[0]) if len(old_prices) == 1 else from_range,
                        'to': '${:.02f}'.format(new_prices[0]) if len(new_prices) == 1 else to_range,
                        'increase': max(new_prices) > max(old_prices)
                    }, **common_data))

            if self.config['quantity_change'] == 'notify':
                new_quantities = list(set(new_quantities))
                old_quantities = list(set(old_quantities))
                if len(new_quantities):
                    changes_map['quantity'].append(dict({
                        'from': '{}'.format(old_quantities[0]) if len(old_quantities) == 1 else '{} - {}'.format(
                            min(old_quantities),
                            max(old_quantities)
                        ),
                        'to': '{}'.format(new_quantities[0]) if len(new_quantities) == 1 else '{} - {}'.format(
                            min(new_quantities),
                            max(new_quantities)
                        ),
                        'increase': max(new_quantities) > max(old_quantities)
                    }, **common_data))
        return changes_map


class ShopifyProductChangeManager(ProductChangeManager):
    def get_product_data(self):
        return get_shopify_product(self.product.store, self.product.shopify_id)

    def handle_product_disappear(self, product_data):
        if self.config['product_disappears'] == 'notify':
            return None
        elif self.config['product_disappears'] == 'unpublish':
            product_data['published'] = False
        elif self.config['product_disappears'] == 'zero_quantity':
            for idx, variant in enumerate(product_data['variants']):
                product_data['variants'][idx]['inventory_quantity'] = 0
                product_data['variants'][idx]['inventory_management'] = 'shopify'
                product_data['variants'][idx]['inventory_policy'] = 'deny'

        return product_data

    def handle_product_appear(self, product_data):
        if self.config['product_disappears'] == 'notify':
            return None
        elif self.config['product_disappears'] == 'unpublish':
            product_data['published'] = True
        elif self.config['product_disappears'] == 'zero_quantity':
            return None

        return product_data

    def handle_variant_quantity_change(self, product_data, variant_change):
        if self.config['quantity_change'] == 'notify':
            return None
        elif self.config['quantity_change'] == 'update':
            idx = self.get_variant(product_data, variant_change)
            if idx is not None:
                product_data['variants'][idx]['inventory_quantity'] = variant_change.get('new_value')
                product_data['variants'][idx]['inventory_management'] = 'shopify'
                product_data['variants'][idx]['inventory_policy'] = 'deny'

        return product_data

    def handle_variant_added(self, product_data, variant_change):
        return None  # This case is not covered with a setting

        idx = self.get_variant(product_data, variant_change)
        if idx is None:
            variant = {}
            variant['sku'] = variant_change.get('sku')
            variant['price'] = variant_change.get('price')
            variant['inventory_quantity'] = variant_change.get('quantity')
            variant['inventory_management'] = 'shopify'
            variant['inventory_policy'] = 'deny'
            product_data['variants'].append(variant)

        return product_data

    def handle_variant_removed(self, product_data, variant_change):
        if self.config['variant_disappears'] == 'notify':
            return None
        elif self.config['variant_disappears'] == 'remove':
            idx = self.get_variant(product_data, variant_change)
            if idx is not None:
                del product_data['variants'][idx]
        elif self.config['variant_disappears'] == 'zero_quantity':
            idx = self.get_variant(product_data, variant_change)
            if idx is not None:
                product_data['variants'][idx]['inventory_quantity'] = 0
                product_data['variants'][idx]['inventory_management'] = 'shopify'
                product_data['variants'][idx]['inventory_policy'] = 'deny'

        return product_data

    def update_product(self, product_data):
        update_endpoint = self.product.store.get_link('/admin/products/{}.json'.format(
            self.product.get_shopify_id()), api=True)
        try:
            if product_data and product_data.get('variants') == []:
                del product_data['variants']

            r = requests.put(update_endpoint, json={'product': product_data})
            r.raise_for_status()

        except Exception as e:
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code not in [401, 402, 403, 404]:
                raven_client.captureException(extra={
                    'rep': r.text,
                    'data': product_data,
                }, tags={
                    'product': self.product.id,
                    'store': self.product.store,
                })
            else:
                raven_client.captureException(extra={
                    'response': e.response.text if hasattr(e, 'response') and hasattr(e.response, 'text') else ''
                })

    def add_price_history(self, variant_id, variant_change):
        history, created = ProductVariantPriceHistory.objects.get_or_create(
            user=self.product.user,
            shopify_product=self.product,
            variant_id=variant_id
        )
        history.add_price(variant_change.get('new_value'), variant_change.get('old_value'))


class CommerceHQProductChangeManager(ProductChangeManager):
    def get_product_data(self):
        return self.product.retrieve()

    def handle_product_disappear(self, product_data):
        if self.config['product_disappears'] == 'notify':
            return None
        elif self.config['product_disappears'] == 'unpublish':
            product_data['is_draft'] = True
        elif self.config['product_disappears'] == 'zero_quantity':
            # TODO: set quantity to zero
            return None

        return product_data

    def handle_product_appear(self, product_data):
        if self.config['product_disappears'] == 'notify':
            return None
        elif self.config['product_disappears'] == 'unpublish':
            product_data['is_draft'] = False
        elif self.config['product_disappears'] == 'zero_quantity':
            return None

        return product_data

    def handle_variant_quantity_change(self, product_data, variant_change):
        if self.config['quantity_change'] == 'notify':
            return None
        elif self.config['quantity_change'] == 'update':
            idx = self.get_variant(product_data, variant_change)
            if idx is not None:
                # TODO: update quantity
                return None

        return product_data

    def handle_variant_added(self, product_data, variant_change):
        return None  # This case is not covered with a setting

        idx = self.get_variant(product_data, variant_change)
        if idx is None:
            variant = {}
            variant['sku'] = variant_change.get('sku')
            variant['price'] = variant_change.get('price')
            # TODO: set quantity
            product_data['variants'].append(variant)

        return product_data

    def handle_variant_removed(self, product_data, variant_change):
        if self.config['variant_disappears'] == 'notify':
            return None
        if self.config['variant_disappears'] == 'remove':
            idx = self.get_variant(product_data, variant_change)
            if idx is not None:
                del product_data['variants'][idx]
        if self.config['variant_disappears'] == 'zero_quantity':
            idx = self.get_variant(product_data, variant_change)
            if idx is not None:
                # TODO: set quantity to zero
                return None

        return product_data

    def update_product(self, product_data):
        try:
            store = self.product.store
            r = store.request.patch(
                url='{}/{}'.format(store.get_api_url('products'), self.product.source_id),
                json={
                    'is_draft': product_data['is_draft'],
                    'variants': product_data['variants'],
                }
            )

            r.raise_for_status()

            self.product.update_data(product_data)

        except Exception as e:
            if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code not in [401, 402, 403, 404]:
                raven_client.captureMessage(extra={
                    'rep': r.text,
                    'data': product_data,
                }, tags={
                    'product': self.product.id,
                    'store': self.product.store,
                })
            else:
                raven_client.captureException(extra={
                    'response': e.response.text if hasattr(e, 'response') and hasattr(e.response, 'text') else ''
                })

    def add_price_history(self, variant_id, variant_change):
        history, created = ProductVariantPriceHistory.objects.get_or_create(
            user=self.product.user,
            chq_product=self.product,
            variant_id=variant_id
        )
        history.add_price(variant_change.get('new_value'), variant_change.get('old_value'))
