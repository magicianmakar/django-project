import simplejson as json
import requests

from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.utils import app_link, safe_float, http_exception_response
from leadgalaxy.models import PriceMarkupRule
from leadgalaxy.utils import get_shopify_product
from product_alerts.utils import variant_index_from_supplier_sku, calculate_price
from zapier_core.utils import user_have_hooks


class ProductChangeManager():
    @classmethod
    def initialize(cls, product_change):
        manager = None
        if product_change.store_type == 'shopify':
            manager = ShopifyProductChangeManager(product_change)
        elif product_change.store_type == 'chq':
            manager = CommerceHQProductChangeManager(product_change)
        elif product_change.store_type == 'gkart':
            manager = GrooveKartProductChangeManager(product_change)
        elif product_change.store_type == 'woo':
            manager = WooProductChangeManager(product_change)
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
        self.markup_rules = PriceMarkupRule.objects.filter(user=self.user.models_user)

        self.config = {
            'product_disappears': self.get_config('alert_product_disappears'),
            'variant_disappears': self.get_config('alert_variant_disappears'),
            'quantity_change': self.get_config('alert_quantity_change'),
            'price_change': self.get_config('alert_price_change'),
            'price_update_method': self.get_config('price_update_method', 'same_margin'),
            'price_update_for_increase': self.get_config('price_update_for_increase', False),
        }

        # Handle old config value
        if self.config['price_change'] == 'update_for_increase':
            self.config['price_change'] = 'update'
            self.config['price_update_for_increase'] = True

        self.removed_variants = []
        self.groovekart_changes = []

    def get_config(self, name, default='notify'):
        value = self.product.get_config().get(name)
        if not value:
            value = self.user.get_config(name, default)

        return value

    def need_update(self):
        """ Return True if the user have any setting that will require a product update """

        for k, v in list(self.config.items()):
            if v not in ['notify', 'none']:
                return True

        return False

    def apply_changes(self):
        try:
            api_product_data = self.get_api_product_data()
            product_data = self.product.parsed

            # Check if the user have any registered Hook before triggering the raw hook signal
            # This reduce the database call significantly because it check first if the user have (in general) any webhooks
            # Otherwise rest_hook will make a database call for each variant change
            if user_have_hooks(self.user):
                self.product_change.send_hook_event(api_product_data)
                self.product_change.send_hook_event_alert()

            if not self.need_update():
                # No need to check for updates, the user doesn't have any setting that will require a product update
                self.product_change.status = 1  # Applied
                self.product_change.save()
                return

            if api_product_data:
                self.product_data_changed = False
                self.apply_product_changes(api_product_data, product_data)
                self.apply_variant_changes(api_product_data, product_data)

                if self.product_data_changed:
                    self.update_product(api_product_data, product_data)

            self.product_change.status = 1  # Applied
            self.product_change.save()

            return product_data

        except Exception:
            self.product_change.status = 2  # Failed
            self.product_change.save()

        return None

    def get_product_data(self):
        pass

    def apply_product_changes(self, api_product_data, product_data):
        if self.product_changes:
            for product_change in self.product_changes:
                if product_change.get('name') == 'offline':
                    if product_change.get('new_value') and not product_change.get('old_value'):  # disappeared
                        self.handle_product_disappear(api_product_data, product_data)
                    elif product_change.get('old_value') and not product_change.get('new_value'):  # appeared
                        self.handle_product_appear(api_product_data, product_data)

    def apply_variant_changes(self, api_product_data, product_data):
        if self.variant_changes:
            for variant_change in self.variant_changes:
                if variant_change.get('name') == 'price':
                    self.handle_variant_price_change(api_product_data, product_data, variant_change)
                elif variant_change.get('name') == 'quantity':
                    self.handle_variant_quantity_change(api_product_data, product_data, variant_change)
                elif variant_change.get('name') == 'var_added':
                    self.handle_variant_added(api_product_data, product_data, variant_change)
                elif variant_change.get('name') == 'var_removed':
                    self.handle_variant_removed(api_product_data, product_data, variant_change)

    def handle_product_disappear(self, api_product_data, product_data):
        pass

    def handle_product_appear(self, api_product_data, product_data):
        pass

    def get_variant(self, api_product_data, variant_change):
        # Example Aliexpress SKU: "15:173#66Blue;5:361386" match to "<OptionGroup>:<OptionID>#<OptionTitle>"
        sku = variant_change.get('sku')
        ships_from_id = variant_change.get('ships_from_id')
        ships_from_title = variant_change.get('ships_from_title')
        return variant_index_from_supplier_sku(self.product, sku, api_product_data.get('variants', []), ships_from_id, ships_from_title)

    def handle_variant_price_change(self, api_product_data, product_data, variant_change):
        pass

    def handle_variant_quantity_change(self, api_product_data, product_data, variant_change):
        pass

    def handle_variant_added(self, api_product_data, product_data, variant_change):
        pass

    def handle_variant_removed(self, api_product_data, product_data, variant_change):
        pass

    def update_product(self, api_product_data, product_data):
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
            }
        elif self.product_change.store_type == 'chq':
            common_data = {
                'images': [self.product.get_image()],
                'title': self.product.title,
                'url': app_link('chq/product', self.product.id),
                'target_url': self.product.commercehq_url,
            }
        elif self.product_change.store_type == 'gkart':
            common_data = {
                'images': [self.product.get_image()],
                'title': self.product.title,
                'url': app_link('gkart/product', self.product.id),
                'target_url': self.product.groovekart_url,
            }
        elif self.product_change.store_type == 'woo':
            common_data = {
                'images': self.product.get_images(),
                'title': self.product.title,
                'url': app_link('woo/product', self.product.id),
                'target_url': self.product.woocommerce_url,
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
    def get_api_product_data(self):
        return get_shopify_product(self.product.store, self.product.shopify_id)

    def handle_product_disappear(self, api_product_data, product_data):
        if self.config['product_disappears'] == 'unpublish':
            self.product_data_changed = True
            api_product_data['published'] = False
            product_data['published'] = False
        elif self.config['product_disappears'] == 'zero_quantity':
            for idx, variant in enumerate(api_product_data.get('variants', [])):
                if variant.get('id'):
                    self.product_data_changed = True
                    self.product.set_variant_quantity(quantity=0, variant_id=variant['id'], variant=variant)

    def handle_product_appear(self, api_product_data, product_data):
        if self.config['product_disappears'] == 'unpublish':
            self.product_data_changed = True
            api_product_data['published'] = True
            product_data['published'] = True
        elif self.config['product_disappears'] == 'zero_quantity':
            pass

    def handle_variant_price_change(self, api_product_data, product_data, variant_change):
        idx = self.get_variant(api_product_data, variant_change)
        if idx is not None:
            variant_id = api_product_data['variants'][idx]['id']
            self.add_price_history(variant_id, variant_change)

        new_value = variant_change.get('new_value')
        old_value = variant_change.get('old_value')

        if self.config['price_change'] == 'update':
            if idx is not None:
                current_price = safe_float(api_product_data['variants'][idx]['price'])
                current_compare_at_price = safe_float(api_product_data['variants'][idx].get('compare_at_price'))

                new_price, new_compare_at_price = calculate_price(
                    self.user,
                    old_value,
                    new_value,
                    current_price,
                    current_compare_at_price,
                    self.config['price_update_method'],
                    self.markup_rules
                )
                if new_price:
                    if self.config['price_update_for_increase']:
                        if new_price > current_price:
                            self.product_data_changed = True
                            api_product_data['variants'][idx]['price'] = new_price
                            api_product_data['variants'][idx]['compare_at_price'] = new_compare_at_price
                    else:
                        self.product_data_changed = True
                        api_product_data['variants'][idx]['price'] = new_price
                        api_product_data['variants'][idx]['compare_at_price'] = new_compare_at_price

    def handle_variant_quantity_change(self, api_product_data, product_data, variant_change):
        if self.config['quantity_change'] == 'update':
            idx = self.get_variant(api_product_data, variant_change)
            if idx is not None:
                self.product_data_changed = True
                self.product.set_variant_quantity(
                    quantity=variant_change.get('new_value'),
                    variant_id=api_product_data['variants'][idx]['id'],
                    variant=api_product_data['variants'][idx],
                )

    def handle_variant_added(self, api_product_data, product_data, variant_change):
        # TODO: Handle this case (Add setting, update logic...)
        # This case is not covered with a setting
        pass

    def handle_variant_removed(self, api_product_data, product_data, variant_change):
        if self.config['variant_disappears'] == 'remove':
            idx = self.get_variant(api_product_data, variant_change)
            if idx is not None:
                self.product_data_changed = True
                self.removed_variants.append(api_product_data['variants'][idx]['id'])
                del api_product_data['variants'][idx]
        elif self.config['variant_disappears'] == 'zero_quantity':
            idx = self.get_variant(api_product_data, variant_change)
            if idx is not None:
                self.product_data_changed = True
                self.product.set_variant_quantity(
                    quantity=0,
                    variant_id=api_product_data['variants'][idx]['id'],
                    variant=api_product_data['variants'][idx]
                )

    def update_product(self, api_product_data, product_data):
        update_endpoint = self.product.store.get_link('/admin/products/{}.json'.format(
            self.product.get_shopify_id()), api=True)

        if api_product_data and api_product_data.get('variants') == []:
            del api_product_data['variants']

        r = requests.put(update_endpoint, json={'product': api_product_data})

        try:
            r.raise_for_status()

            self.product.update_data(product_data)
        except:
            if r.status_code not in [401, 402, 403, 404, 429]:
                raven_client.captureException(extra={
                    'rep': r.text,
                    'data': api_product_data,
                }, tags={
                    'product': self.product.id,
                    'store': self.product.store,
                })

    def add_price_history(self, variant_id, variant_change):
        pass


class CommerceHQProductChangeManager(ProductChangeManager):
    def get_api_product_data(self):
        return self.product.retrieve()

    def handle_product_disappear(self, api_product_data, product_data):
        if self.config['product_disappears'] == 'unpublish':
            self.product_data_changed = True
            product_data['published'] = False
            api_product_data['is_draft'] = True
        elif self.config['product_disappears'] == 'zero_quantity':
            # TODO: set quantity to zero
            pass

    def handle_product_appear(self, api_product_data, product_data):
        if self.config['product_disappears'] == 'unpublish':
            self.product_data_changed = True
            product_data['published'] = True
            api_product_data['is_draft'] = False
        elif self.config['product_disappears'] == 'zero_quantity':
            pass

    def handle_variant_price_change(self, api_product_data, product_data, variant_change):
        idx = self.get_variant(api_product_data, variant_change)
        if idx is not None:
            variant_id = api_product_data['variants'][idx]['id']
            self.add_price_history(variant_id, variant_change)

        new_value = variant_change.get('new_value')
        old_value = variant_change.get('old_value')

        if self.config['price_change'] == 'update':
            if idx is not None:
                current_price = safe_float(api_product_data['variants'][idx]['price'])
                current_compare_at_price = safe_float(api_product_data['variants'][idx].get('compare_price'))

                new_price, new_compare_at_price = calculate_price(
                    self.user,
                    old_value,
                    new_value,
                    current_price,
                    current_compare_at_price,
                    self.config['price_update_method'],
                    self.markup_rules
                )
                if new_price:
                    if self.config['price_update_for_increase']:
                        if new_price > current_price:
                            self.product_data_changed = True
                            api_product_data['variants'][idx]['price'] = new_price
                            api_product_data['variants'][idx]['compare_price'] = new_compare_at_price
                    else:
                        self.product_data_changed = True
                        api_product_data['variants'][idx]['price'] = new_price
                        api_product_data['variants'][idx]['compare_price'] = new_compare_at_price
            elif api_product_data.get('is_multi') is False:
                current_price = safe_float(api_product_data['price'])
                current_compare_at_price = safe_float(api_product_data.get('compare_price'))

                new_price, new_compare_at_price = calculate_price(
                    self.user,
                    old_value,
                    new_value,
                    current_price,
                    current_compare_at_price,
                    self.config['price_update_method'],
                    self.markup_rules
                )
                if new_price:
                    if self.config['price_update_for_increase']:
                        if new_price > current_price:
                            self.product_data_changed = True
                            product_data['price'] = new_price
                            product_data['compare_at_price'] = new_compare_at_price
                            api_product_data['price'] = new_price
                            api_product_data['compare_price'] = new_compare_at_price
                    else:
                        self.product_data_changed = True
                        product_data['price'] = new_price
                        product_data['compare_at_price'] = new_compare_at_price
                        api_product_data['price'] = new_price
                        api_product_data['compare_price'] = new_compare_at_price

    def handle_variant_quantity_change(self, api_product_data, product_data, variant_change):
        if self.config['quantity_change'] == 'update':
            idx = self.get_variant(api_product_data, variant_change)
            if idx is not None:
                # TODO: update quantity
                pass

    def handle_variant_added(self, api_product_data, product_data, variant_change):
        # TODO: Handle this case (Add setting, update logic...)
        # This case is not covered with a setting
        pass

    def handle_variant_removed(self, api_product_data, product_data, variant_change):
        if self.config['variant_disappears'] == 'remove':
            idx = self.get_variant(api_product_data, variant_change)
            if idx is not None:
                self.product_data_changed = True
                self.removed_variants.append(api_product_data['variants'][idx]['id'])
                del api_product_data['variants'][idx]

        elif self.config['variant_disappears'] == 'zero_quantity':
            idx = self.get_variant(api_product_data, variant_change)
            if idx is not None:
                # TODO: set quantity to zero
                pass

    def update_product(self, api_product_data, product_data):
        store = self.product.store
        r = store.request.patch(
            url='{}/{}'.format(store.get_api_url('products'), self.product.source_id),
            json={
                'is_draft': api_product_data['is_draft'],
                'variants': api_product_data['variants'],
            }
        )

        try:
            r.raise_for_status()

            self.product.update_data(product_data)

        except Exception as e:
            if r.status_code not in [401, 402, 403, 404, 429]:
                raven_client.captureMessage(extra={
                    'rep': r.text,
                    'data': api_product_data,
                }, tags={
                    'product': self.product.id,
                    'store': self.product.store,
                })
            else:
                raven_client.captureException(extra=http_exception_response(e))

    def add_price_history(self, variant_id, variant_change):
        pass


class GrooveKartProductChangeManager(ProductChangeManager):
    def get_api_product_data(self):
        return self.product.retrieve()

    def handle_product_disappear(self, api_product_data, product_data):
        if self.config['product_disappears'] == 'unpublish':
            self.product_data_changed = True
            product_data['published'] = False
            self.groovekart_changes.append({
                'api_url': 'products.json',
                'api_data': {
                    'product': {
                        'id': self.product.source_id,
                        'action': 'product_status',
                        'active': False,
                    }
                }
            })
        elif self.config['product_disappears'] == 'zero_quantity':
            # GrooveKart doesn't support quantity management
            pass

    def handle_product_appear(self, api_product_data, product_data):
        if self.config['product_disappears'] == 'unpublish':
            self.product_data_changed = True
            product_data['published'] = True
            self.groovekart_changes.append({
                'api_url': 'products.json',
                'api_data': {
                    'product': {
                        'id': self.product.source_id,
                        'action': 'product_status',
                        'active': True,
                    }
                }
            })
        elif self.config['product_disappears'] == 'zero_quantity':
            # GrooveKart doesn't support quantity management
            pass

    def handle_variant_price_change(self, api_product_data, product_data, variant_change):
        idx = self.get_variant(api_product_data, variant_change)
        if idx is not None:
            variant_id = api_product_data['variants'][idx]['id_product_variant']
            self.add_price_history(variant_id, variant_change)

        new_value = variant_change.get('new_value')
        old_value = variant_change.get('old_value')

        if self.config['price_change'] == 'update':
            if idx is not None:
                current_price = safe_float(api_product_data['variants'][idx]['price'])
                current_compare_at_price = safe_float(api_product_data['variants'][idx].get('compare_at_price'))

                new_price, new_compare_at_price = calculate_price(
                    self.user,
                    old_value,
                    new_value,
                    current_price,
                    current_compare_at_price,
                    self.config['price_update_method'],
                    self.markup_rules
                )
                if new_price:
                    if self.config['price_update_for_increase']:
                        if new_price > current_price:
                            self.product_data_changed = True
                            api_product_data['variants'][idx]['price'] = new_price
                            api_product_data['variants'][idx]['compare_at_price'] = new_compare_at_price
                            self.groovekart_changes.append({
                                'api_url': 'variants.json',
                                'api_data': {
                                    'action': 'update',
                                    'product_id': self.product.source_id,
                                    'variants': [
                                        {
                                            'id': api_product_data['variants'][idx]['id_product_variant'],
                                            'price': new_price,
                                            'compare_at_price': new_compare_at_price
                                        }
                                    ],
                                }
                            })
                    else:
                        self.product_data_changed = True
                        api_product_data['variants'][idx]['price'] = new_price
                        api_product_data['variants'][idx]['compare_at_price'] = new_compare_at_price
                        self.groovekart_changes.append({
                            'api_url': 'variants.json',
                            'api_data': {
                                'action': 'update',
                                'product_id': self.product.source_id,
                                'variants': [
                                    {
                                        'id': api_product_data['variants'][idx]['id_product_variant'],
                                        'price': new_price,
                                        'compare_at_price': new_compare_at_price
                                    }
                                ],
                            }
                        })
            elif len(api_product_data.get('variants', [])) == 0:
                current_price = safe_float(api_product_data['price'])
                current_compare_at_price = safe_float(api_product_data.get('compare_default_price'))

                new_price, new_compare_at_price = calculate_price(
                    self.user,
                    old_value,
                    new_value,
                    current_price,
                    current_compare_at_price,
                    self.config['price_update_method'],
                    self.markup_rules
                )
                if new_price:
                    if self.config['price_update_for_increase']:
                        if new_price > current_price:
                            self.product_data_changed = True
                            product_data['price'] = new_price
                            product_data['compare_at_price'] = new_compare_at_price
                            api_product_data['price'] = new_price
                            api_product_data['compare_default_price'] = new_compare_at_price
                            self.groovekart_changes.append({
                                'api_url': 'products.json',
                                'api_data': {
                                    'product': {
                                        'action': 'update_product',
                                        'id': self.product.source_id,
                                        'price': new_price,
                                        'compare_default_price': new_compare_at_price,
                                    },
                                }
                            })
                    else:
                        self.product_data_changed = True
                        product_data['price'] = new_price
                        product_data['compare_at_price'] = new_compare_at_price
                        api_product_data['price'] = new_price
                        api_product_data['compare_default_price'] = new_compare_at_price
                        self.groovekart_changes.append({
                            'api_url': 'products.json',
                            'api_data': {
                                'product': {
                                    'action': 'update_product',
                                    'id': self.product.source_id,
                                    'price': new_price,
                                    'compare_default_price': new_compare_at_price,
                                },
                            }
                        })

    def handle_variant_quantity_change(self, api_product_data, product_data, variant_change):
        # GrooveKart doesn't support quantity management
        pass

    def handle_variant_added(self, api_product_data, product_data, variant_change):
        # TODO: Handle this case (Add setting, update logic...)
        # This case is not covered with a setting
        pass

    def handle_variant_removed(self, api_product_data, product_data, variant_change):
        if self.config['variant_disappears'] == 'remove':
            idx = self.get_variant(api_product_data, variant_change)
            if idx is not None:
                # self.product_data_changed = True
                # TODO
                pass
        elif self.config['variant_disappears'] == 'zero_quantity':
            # GrooveKart doesn't support quantity management
            pass

    def update_product(self, api_product_data, product_data):
        store = self.product.store
        try:
            for groovekart_change in self.groovekart_changes:
                api_endpoint = store.get_api_url(groovekart_change['api_url'])
                r = store.request.post(api_endpoint, json=groovekart_change['api_data'])
                r.raise_for_status()
            self.product.update_data(product_data)

        except Exception as e:
            if r.status_code not in [401, 402, 403, 404, 429]:
                raven_client.captureMessage(extra={
                    'rep': r.text,
                    'data': api_product_data,
                }, tags={
                    'product': self.product.id,
                    'store': self.product.store,
                })
            else:
                raven_client.captureException(extra=http_exception_response(e))

    def add_price_history(self, variant_id, variant_change):
        pass


class WooProductChangeManager(ProductChangeManager):
    def get_api_product_data(self):
        return self.product.retrieve()

    def handle_product_disappear(self, api_product_data, product_data):
        if self.config['product_disappears'] == 'unpublish':
            self.product_data_changed = True
            product_data['published'] = False
            api_product_data['status'] = 'draft'
        elif self.config['product_disappears'] == 'zero_quantity':
            api_product_data['stock_status'] = 'outofstock'

    def handle_product_appear(self, api_product_data, product_data):
        if self.config['product_disappears'] == 'unpublish':
            self.product_data_changed = True
            product_data['published'] = True
            api_product_data['status'] = 'publish'
        elif self.config['product_disappears'] == 'zero_quantity':
            api_product_data['stock_status'] = 'instock'

    def handle_variant_price_change(self, api_product_data, product_data, variant_change):
        idx = self.get_variant(api_product_data, variant_change)
        if idx is not None:
            variant_id = api_product_data['variants'][idx]['id']
            if variant_id > 0:
                self.add_price_history(variant_id, variant_change)

        new_value = variant_change.get('new_value')
        old_value = variant_change.get('old_value')

        if self.config['price_change'] == 'update':
            if variant_id > 0:
                current_price = safe_float(api_product_data['variants'][idx]['sale_price'])
                current_compare_at_price = safe_float(api_product_data['variants'][idx].get('regular_price'))

                new_price, new_compare_at_price = calculate_price(
                    self.user,
                    old_value,
                    new_value,
                    current_price,
                    current_compare_at_price,
                    self.config['price_update_method'],
                    self.markup_rules
                )
                if self.config['price_update_for_increase']:
                    if new_price > current_price:
                        self.product_data_changed = True
                        product_data['variants'][idx]['sale_price'] = new_price
                        product_data['variants'][idx]['regular_price'] = new_compare_at_price
                        api_product_data['variants'][idx]['sale_price'] = str(new_price)
                        api_product_data['variants'][idx]['regular_price'] = str(new_compare_at_price)
                else:
                    self.product_data_changed = True
                    product_data['variants'][idx]['sale_price'] = new_price
                    product_data['variants'][idx]['regular_price'] = new_compare_at_price
                    api_product_data['variants'][idx]['sale_price'] = str(new_price)
                    api_product_data['variants'][idx]['regular_price'] = str(new_compare_at_price)
            elif len(api_product_data.get('variants', [])) == 0 or variant_id < 0:
                current_price = safe_float(api_product_data['sale_price'])
                current_compare_at_price = safe_float(api_product_data.get('regular_price'))

                new_price, new_compare_at_price = calculate_price(
                    self.user,
                    old_value,
                    new_value,
                    current_price,
                    current_compare_at_price,
                    self.config['price_update_method'],
                    self.markup_rules
                )
                if self.config['price_update_for_increase']:
                    if new_price > current_price:
                        self.product_data_changed = True
                        product_data['price'] = new_price
                        product_data['compare_at_price'] = new_compare_at_price
                        api_product_data['sale_price'] = str(new_price)
                        api_product_data['regular_price'] = str(new_compare_at_price)
                else:
                    self.product_data_changed = True
                    product_data['price'] = new_price
                    product_data['compare_at_price'] = new_compare_at_price
                    api_product_data['sale_price'] = str(new_price)
                    api_product_data['regular_price'] = str(new_compare_at_price)

    def handle_variant_quantity_change(self, api_product_data, product_data, variant_change):
        if self.config['quantity_change'] == 'update':
            idx = self.get_variant(api_product_data, variant_change)
            if idx is not None:
                variant_id = api_product_data['variants'][idx]['id']
            if variant_id > 0:
                self.product_data_changed = True
                product_data['variants'][idx]['stock_quantity'] = variant_change.get('new_value')
                api_product_data['variants'][idx]['stock_quantity'] = variant_change.get('new_value')
            elif len(api_product_data.get('variants', [])) == 0 or variant_id < 0:
                api_product_data['stock_quantity'] = variant_change.get('new_value')

    def handle_variant_added(self, api_product_data, product_data, variant_change):
        # TODO: Handle this case (Add setting, update logic...)
        # This case is not covered with a setting
        pass

    def handle_variant_removed(self, api_product_data, product_data, variant_change):
        idx = self.get_variant(api_product_data, variant_change)
        if idx is not None:
            variant_id = api_product_data['variants'][idx]['id']
        if self.config['variant_disappears'] == 'remove':
            if variant_id > 0:
                self.product_data_changed = True
                self.removed_variants.append(api_product_data['variants'][idx]['id'])
                del product_data['variants'][idx]
                del api_product_data['variants'][idx]
        elif self.config['variant_disappears'] == 'zero_quantity':
            if variant_id > 0:
                self.product_data_changed = True
                product_data['variants'][idx]['stock_quantity'] = 0
                api_product_data['variants'][idx]['stock_quantity'] = 0

    def update_product(self, api_product_data, product_data):
        update_endpoint = 'products/{}'.format(self.product.source_id)
        variants_update_endpoint = 'products/{}/variations/batch'.format(self.product.source_id)

        try:
            r = self.product.store.wcapi.put(update_endpoint, api_product_data)
            r.raise_for_status()
            r = self.product.store.wcapi.put(variants_update_endpoint, {
                'update': api_product_data['variants'],
                'delete': self.removed_variants,
            })
            r.raise_for_status()

            self.product.update_data(product_data)
        except:
            if r.status_code not in [401, 402, 403, 404, 429]:
                raven_client.captureException(extra={
                    'rep': r.text,
                    'data': api_product_data,
                }, tags={
                    'product': self.product.id,
                    'store': self.product.store,
                })

    def add_price_history(self, variant_id, variant_change):
        pass
