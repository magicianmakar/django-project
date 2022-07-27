import json

from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.functional import cached_property

from shopified_core.utils import app_link, get_store_api
from lib.exceptions import capture_exception


class AccountBalance(models.Model):
    user = models.OneToOneField(User, related_name='logistics_balance', on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=10, decimal_places=2)


class AccountCredit(models.Model):
    balance = models.ForeignKey(AccountBalance, related_name='credits', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    stripe_charge_id = models.CharField(max_length=255, unique=True, editable=False, verbose_name='Stripe Charge ID')

    def __str__(self):
        return f"{self.balance.user.email} - ${self.amount:,.2f}"


class Account(models.Model):
    user = models.ForeignKey(User, related_name='logistics_accounts', on_delete=models.CASCADE)
    source_id = models.CharField(max_length=64, null=True, blank=True)
    source_data = models.TextField(blank=True, default='')
    api_key = models.CharField(max_length=255, default='', blank=True)
    test_api_key = models.CharField(max_length=255, default='', blank=True)

    def __str__(self):
        return self.user.email

    def create_source(self):
        if self.source_id:
            return False

        from .utils import get_root_easypost_api
        result = get_root_easypost_api(debug=False).User.create(
            name=f"{self.user.first_name} {self.user.last_name}"
        )
        self.source_id = result['id']
        self.source_data = json.dumps(result.to_dict())
        for key in result['api_keys']:
            if key['object'] != 'ApiKey':
                continue
            if key['mode'] == 'production':
                self.api_key = key['key']
            if key['mode'] == 'test':
                self.test_api_key = key['key']

        if not self.api_key:
            raise Exception('Easypost account without API key')
        self.save()


class CarrierType(models.Model):
    label = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    source = models.CharField(max_length=100)
    updated_at = models.DateTimeField(auto_now=True)
    fields = models.TextField(default='[]', help_text='''Credentials fields in format <pre>
    [{
        "name": "api_key",
        "label": "Api Key",
        "type": "password/text"
    }]</pre>''')
    logo_url = models.TextField(blank=True, default='')

    class Meta:
        ordering = ('label',)

    def __str__(self):
        return f"{self.label} - {self.name}"

    def get_fields(self):
        try:
            return json.loads(self.fields)
        except:
            return []

    def to_dict(self):
        return dict(
            id=self.id,
            label=self.label,
            name=self.name,
            fields=self.get_fields(),
        )


class Carrier(models.Model):
    account = models.ForeignKey(Account, null=True, blank=True, related_name='carriers', on_delete=models.CASCADE)
    carrier_type = models.ForeignKey(CarrierType, null=True, blank=True, on_delete=models.SET_NULL)
    description = models.CharField(max_length=512)
    reference = models.CharField(max_length=512)
    credentials = models.TextField(default='{}')
    source_id = models.CharField(max_length=64, blank=True, default='')

    class Meta:
        unique_together = ('account', 'reference')

    def get_credentials(self):
        try:
            return json.loads(self.credentials)
        except:
            return {}

    def create_source(self):
        from .utils import get_easypost_api
        if self.source_id:
            return {'errors': ['Carrier already exists']}

        api = get_easypost_api(self.account.user, debug=False)
        try:
            result = api.CarrierAccount.create(
                type=self.carrier_type.name,
                description=self.description,
                reference=self.reference,
                credentials=self.get_credentials(),
            )
            self.source_id = result['id']
            self.save()
            return {'success': True}

        except api.Error as e:
            return {'errors': [e.message]}

    def get_source(self):
        from .utils import get_easypost_api
        api = get_easypost_api(self.account.user, debug=False)
        return api.CarrierAccount.retrieve(self.source_id)


class WarehouseIsActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(deleted_at__isnull=True)


class Warehouse(models.Model):
    objects = WarehouseIsActiveQuerySet.as_manager()

    user = models.ForeignKey(User, related_name='warehouses', on_delete=models.CASCADE)
    address_source_id = models.CharField(max_length=64, blank=True, default='')
    name = models.CharField(max_length=512, verbose_name="Resident's Full Name")
    company = models.CharField(max_length=512, blank=True)
    address1 = models.CharField(max_length=512)
    address2 = models.CharField(max_length=512, blank=True)
    city = models.CharField(max_length=512)
    province = models.CharField(max_length=512, blank=True)
    zip = models.CharField(max_length=50)
    country_code = models.CharField(max_length=10)
    country = models.CharField(max_length=255)
    phone = models.CharField(max_length=100, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    @property
    def logistics_address(self):
        from logistics.utils import Address
        return Address(
            user=self.user,
            address_source_id=self.address_source_id,
            name=self.name,
            company=self.company,
            address1=self.address1,
            address2=self.address2,
            city=self.city,
            province=self.province,
            zip=self.zip,
            country_code=self.country_code,
            phone=self.phone,
        )

    def source_address(self):
        address = self.logistics_address
        result = address.create()
        self.address_source_id = result['address_source_id']
        return result

    def get_full_name(self):
        return f"{self.name} ({self.city}, {self.country_code})"

    def to_dict(self):
        return {
            'id': self.id,
            'address_source_id': self.address_source_id,
            'name': self.name,
            'company': self.company,
            'address1': self.address1,
            'address2': self.address2,
            'city': self.city,
            'province': self.province,
            'zip': self.zip,
            'country_code': self.country_code,
            'country': self.country,
            'phone': self.phone,
        }


class Product(models.Model):
    user = models.ForeignKey(User, related_name='logistics_products', on_delete=models.CASCADE)
    title = models.CharField(max_length=512)
    image_urls = models.TextField(blank=True, default='')
    hs_tariff = models.CharField(max_length=32, blank=True, default='')
    variants_map = models.TextField(default='[]')

    @cached_property
    def image(self):
        images = self.images()
        return images[0] if images else ''

    @cached_property
    def variants_connection(self):
        # TODO: use simple variants map for exporting the product and specific variants for mapping them in Dropified
        return [{
            'title': 'Variant',
            'values': [v.to_dict() for v in self.variants.all()]
        }]

    def images(self):
        try:
            return json.loads(self.image_urls)
        except:
            return []

    def get_variants_map(self):
        try:
            return json.loads(self.variants_map)
        except:
            return []


class Variant(models.Model):
    product = models.ForeignKey(Product, related_name='variants', on_delete=models.CASCADE)
    title = models.CharField(max_length=512)
    sku = models.CharField(max_length=512)
    weight = models.DecimalField(decimal_places=3, max_digits=6, default=0, verbose_name='Weight (oz)')
    length = models.DecimalField(decimal_places=3, max_digits=6, default=0, verbose_name='Length (inches)')
    width = models.DecimalField(decimal_places=3, max_digits=6, default=0, verbose_name='Width (inches)')
    height = models.DecimalField(decimal_places=3, max_digits=6, default=0, verbose_name='Height (inches)')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'sku': self.sku,
            'weight': self.weight or 0,
            'length': self.length or 0,
            'width': self.width or 0,
            'height': self.height or 0,
        }


class SupplierIsActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(warehouse__deleted_at__isnull=True)


class Supplier(models.Model):
    objects = SupplierIsActiveQuerySet.as_manager()

    warehouse = models.ForeignKey(Warehouse, related_name='products', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name='suppliers', on_delete=models.CASCADE)
    source_ids = models.CharField(max_length=512, blank=True, default='')

    @cached_property
    def variants_data(self):
        data = {'prices': [], 'inventory': []}
        for listing in self.listings.all():
            data['prices'].append(listing.price)
            data['inventory'].append(listing.inventory)
        return data

    @cached_property
    def variants_connection(self):
        return [{
            'title': 'Variant',
            'values': [listing.to_dict() for listing in self.listings.all()]
        }]

    def total_inventory(self):
        return sum([i for i in self.variants_data['inventory'] if i is not None])

    def price_range(self):
        prices = self.variants_data['prices']
        if not prices:
            return ''

        price_min = min(prices)
        price_max = max(prices)
        if price_min == price_max:
            return price_min
        return f'{price_min} - {price_max}'

    @property
    def store_api_request(self):
        if not hasattr(self, '_store_api_request') or not self._store_api_request:
            class MockRequest:
                META = {}

            self._store_api_request = MockRequest()
        return self._store_api_request

    def get_store_api(self, store_type):
        if not hasattr(self, '_store_api') or not self._store_api:
            self._store_api = get_store_api(store_type)
        return self._store_api

    def is_sourced(self, source_id):
        source_ids = self.source_ids.split(',')
        found_source_id = [s for s in source_ids if source_id in s]
        found_source_id = found_source_id[0].split('_')[-1] if len(found_source_id) > 0 else False
        return found_source_id

    def add_source(self, source_id):
        source_ids = self.source_ids.split(',')
        raw_source_id = '_'.join(source_id.split('_')[:-1])
        if raw_source_id in source_ids:
            source_ids.remove(raw_source_id)
        source_ids.append(source_id)
        self.source_ids = ','.join(source_ids)
        self.save()

    def connect_supplier(self, store_type, store_id, dropified_id):
        search_source_id = f'{store_type}_{store_id}_{dropified_id}_'
        if self.is_sourced(search_source_id):
            return True

        link = app_link(reverse('logistics:supplier', kwargs={'supplier_id': self.id}))
        data = {
            'original-link': link,
            'supplier-name': '3PL',
            'supplier-link': '',
            'export': None,
            'product': dropified_id,
        }

        result = {}
        try:
            endpoint = 'post_product_metadata' if store_type == 'shopify' else 'post_supplier'
            store_api = self.get_store_api(store_type)
            endpoint = getattr(store_api, endpoint)
            response = endpoint(self.store_api_request, self.warehouse.user, data)
            result = json.loads(response.content.decode('utf8'))
            if response.status_code == 200 and result.get('export'):
                self.add_source(f"{search_source_id}{result.get('export')}")
            elif isinstance(result, dict) and result.get('error'):
                return result
            else:
                raise Exception(result)
        except:
            capture_exception()

        return result

    def connect_product(self, store_type, store_id, product_id):
        search_source_id = f'{store_type}_{store_id}_{product_id}_'
        if self.is_sourced(search_source_id):
            return True

        link = app_link(reverse('logistics:supplier', kwargs={'supplier_id': self.id}))
        data = {
            'supplier': link,
            'vendor_name': '3PL',
            'vendor_url': '',
            'store': store_id,
            'product': product_id,
        }

        result = {}
        try:
            store_api = self.get_store_api(store_type)
            response = store_api.post_import_product(self.store_api_request, self.warehouse.user, data)
            result = json.loads(response.content.decode("utf-8"))
            if response.status_code == 200 and result.get('export'):
                self.add_source(f"{search_source_id}{result.get('export')}")
            elif isinstance(result, dict) and result.get('error'):
                return result
            else:
                raise Exception(result)
        except:
            capture_exception()

        return result


class Listing(models.Model):
    supplier = models.ForeignKey(Supplier, related_name='listings', on_delete=models.CASCADE)
    variant = models.ForeignKey(Variant, related_name='listings', on_delete=models.CASCADE)
    inventory = models.IntegerField(null=True, blank=True)  # TODO
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True)

    def to_dict(self):
        return {
            **self.variant.to_dict(),  # Do not override variant id in this dict
            'warehouse_id': self.supplier.warehouse_id,
            'variant_id': self.variant_id,
            'inventory': self.inventory,
            'price': self.price,
        }


class Package(models.Model):
    length = models.DecimalField(decimal_places=3, max_digits=6, verbose_name='Length (inches)')
    width = models.DecimalField(decimal_places=3, max_digits=6, verbose_name='Width (inches)')
    height = models.DecimalField(decimal_places=3, max_digits=6, verbose_name='Height (inches)')


class Order(models.Model):
    SHOPIFY = 'shopify'
    CHQ = 'chq'
    WOO = 'woo'
    EBAY = 'ebay'
    FB = 'fb'
    GKART = 'gkart'
    BIGCOMMERCE = 'bigcommerce'
    STORE_TYPES = [
        (SHOPIFY, 'Shopify'),
        (CHQ, 'CommerceHQ'),
        (WOO, 'WooCommerce'),
        (EBAY, 'eBay'),
        (FB, 'Facebook'),
        (GKART, 'GrooveKart'),
        (BIGCOMMERCE, 'BigCommerce')
    ]
    package = models.ForeignKey(Package, related_name='orders', null=True, blank=True, on_delete=models.SET_NULL)
    warehouse = models.ForeignKey(Warehouse, related_name='orders', on_delete=models.CASCADE)
    store_type = models.CharField(max_length=15, choices=STORE_TYPES, default=SHOPIFY)
    store_id = models.IntegerField()
    store_order_number = models.CharField(max_length=30, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    to_address_hash = models.CharField(max_length=255)
    to_address = models.TextField(default='{}')
    from_address = models.TextField(default='{}')
    weight = models.DecimalField(decimal_places=3, max_digits=6, default=0, verbose_name='Weight (oz)')
    length = models.DecimalField(decimal_places=3, max_digits=6, default=0, verbose_name='Length (inches)')
    width = models.DecimalField(decimal_places=3, max_digits=6, default=0, verbose_name='Width (inches)')
    height = models.DecimalField(decimal_places=3, max_digits=6, default=0, verbose_name='Height (inches)')
    shipment_data = models.TextField(default='{}')
    rate_id = models.CharField(max_length=255, blank=True, default='')
    tracking_number = models.CharField(max_length=255, blank=True, default='')
    source_label_url = models.TextField(blank=True, default='')

    shipment_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_dropified = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=False)

    @property
    def label_url(self):
        if not self.source_label_url:
            return ''
        return app_link(reverse('logistics:label', kwargs={'order_id': self.id}))

    @property
    def status(self):
        if self.tracking_number:
            return 'D_SHIPPED'

        if self.rate_id:
            return 'D_PAID'

        return 'D_PENDING_PAYMENT'

    def pack(self, package=None, force=False):
        if not package:
            return False

        self.weight = float(package.get('weight'))
        self.length = float(package.get('length'))
        self.width = float(package.get('width'))
        self.height = float(package.get('height'))

        from logistics.utils import Shipment
        shipment = Shipment(self, user=self.warehouse.user)
        shipment.create(force=force)

    def pay(self, rate_id):
        self.rate_id = rate_id
        from logistics.utils import Shipment
        shipment = Shipment(self, user=self.warehouse.user)
        is_paid = shipment.pay()
        if not is_paid:
            return False

        for item in self.items.all():
            item.save_order_track()

        return True

    def get_address(self, address_type='to'):
        if address_type == 'to':
            address = self.to_address
        else:
            address = self.from_address

        try:
            return json.loads(address)
        except:
            return {}

    def get_shipment(self):
        try:
            return json.loads(self.shipment_data)
        except:
            return []

    @cached_property
    def order_data_ids(self):
        return [item.order_data_id for item in self.items.all()]

    def to_dict(self):
        items = []
        order_data_ids = []
        for item in self.items.all():
            order_data_ids.append(item.order_data_id)
            items.append(item.to_dict())

        return {
            'id': self.id,
            'order_data_ids': order_data_ids,
            'warehouse_id': self.warehouse_id,
            'to_address_hash': self.to_address_hash,
            'to_address': self.get_address(),
            'from_address': self.get_address('from'),
            'weight': self.weight,
            'length': self.length,
            'width': self.width,
            'height': self.height,
            'items': items,
            'rate_id': self.rate_id,
            'shipment': self.get_shipment(),
            'label_url': self.label_url,
        }


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    listing = models.ForeignKey(Listing, blank=True, null=True, related_name='purchases', on_delete=models.SET_NULL)
    order_data_id = models.CharField(max_length=255, blank=True, null=True)
    order_track_id = models.CharField(max_length=255, blank=True, default='')
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(default=1)
    is_inventory_tracked = models.BooleanField(default=False)
    title = models.TextField(blank=True, default='')
    weight = models.DecimalField(decimal_places=3, max_digits=6, default=0, verbose_name='Weight (oz)')
    hs_tariff = models.CharField(max_length=32, blank=True, default='')  # hs_code
    country_code = models.CharField(max_length=10, blank=True, default='')

    @property
    def store_api(self):
        ids = self.get_store_ids()
        if not hasattr(self, '_store_api') or not self._store_api:
            self._store_api = get_store_api(ids[0])
        return self._store_api

    @property
    def store_api_request(self):
        if not hasattr(self, '_store_api_request') or not self._store_api_request:
            class MockRequest:
                META = {}

            self._store_api_request = MockRequest()
        return self._store_api_request

    def to_dict(self):
        order_item = {
            'title': self.title,
            'hs_tariff': self.hs_tariff,
            'weight': self.weight,
            'country_code': self.country_code,
            'order_data_id': '_'.join(self.order_data_id.split('_')[1:]),
            'warehouse_id': self.order.warehouse_id,
            'inventory': None,
            'variant_id': None,
        }

        if self.listing:
            order_item['weight'] = order_item['weight'] or self.listing.variant.weight * self.quantity
            order_item['hs_tariff'] = order_item['hs_tariff'] or self.listing.variant.product.hs_tariff
            order_item['inventory'] = self.listing.inventory
            order_item['variant_id'] = self.listing.variant_id

        return order_item

    def get_store_ids(self):
        store_type, store_id, order_id, item_id = self.order_data_id.split('_')
        return store_type, store_id, order_id, item_id

    def save_order_track(self):
        if not self.order_track_id:
            if not self.is_inventory_tracked and self.listing and self.listing.inventory is not None:
                self.listing.inventory -= self.quantity
                self.listing.save()
                self.is_inventory_tracked = True
                self.save()
            self.create_tracking()

        self.update_tracking()
        self.save()

    def create_tracking(self):
        store_type, store_id, order_id, item_id = self.get_store_ids()
        api_data = {
            'store': store_id,
            'order_id': order_id,
            'line_id': item_id,
            'aliexpress_order_id': str(self.order.id),
            'source_type': 'dropified-logistics',
        }

        try:
            response = self.store_api.post_order_fulfill(self.store_api_request, self.order.warehouse.user, api_data)
            result = json.loads(response.content.decode("utf-8"))
            if response.status_code == 200 and result.get('order_track_id'):
                self.order_track_id = result['order_track_id']
            else:
                raise Exception(result)
        except:
            capture_exception()

    def update_tracking(self):
        store_type, store_id, order_id, item_id = self.get_store_ids()
        api_data = {
            'store': store_id,
            'status': self.order.status,
            'order': self.order_track_id,
            'order_details': json.dumps({}),  # TODO: add prices for profit dashboard and fulfillment fees
            'tracking_number': self.order.tracking_number,
            'source_id': str(self.order.id),
            'source_type': 'dropified-logistics',
            'bundle': False,  # TODO: add bundle support
        }

        try:
            response = self.store_api.post_order_fulfill_update(self.store_api_request, self.order.warehouse.user, api_data)
            if response.status_code != 200:
                result = json.loads(response.content.decode("utf-8"))
                raise Exception(result)
        except:
            capture_exception()
