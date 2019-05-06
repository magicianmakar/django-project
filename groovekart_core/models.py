import json
import re
import textwrap

from urllib.parse import urlparse

from requests import Session
from pusher import Pusher

from django.db import models
from django.db.models import Q
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string

from product_alerts.utils import monitor_product
from shopified_core.decorators import add_to_class
from shopified_core.utils import (
    get_domain,
    safe_str,
    base64_encode,
    dict_val,
)


@add_to_class(User, 'get_gkart_boards')
def user_get_gkart_boards(self):
    if self.is_subuser:
        return self.profile.subuser_parent.get_gkart_boards()
    else:
        return self.groovekartboard_set.all().order_by('title')


class GrooveKartStoreSession(Session):
    def __init__(self, store, *args, **kwargs):
        self._store = store
        super().__init__(*args, **kwargs)

    def post(self, *args, **kwargs):
        kwargs = self.update_json_data(kwargs)
        return super().post(*args, **kwargs)

    def update_json_data(self, kwargs):
        auth_token, api_key = self._store.api_token, self._store.api_key
        kwargs['json'].update({'auth_token': auth_token, 'api_key': api_key})

        return kwargs


class GrooveKartStore(models.Model):
    class Meta:
        verbose_name = 'GrooveKart Store'

    user = models.ForeignKey(User)
    title = models.CharField(max_length=300, blank=True, default='')
    api_url = models.CharField(max_length=512)
    api_key = models.CharField(max_length=300)
    api_token = models.CharField(max_length=300)
    is_active = models.BooleanField(default=True)
    store_hash = models.CharField(default='', max_length=50, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    @property
    def request(self):
        return GrooveKartStoreSession(self)

    def save(self, *args, **kwargs):
        if not self.store_hash:
            self.store_hash = get_random_string(32, 'abcdef0123456789')

        super().save(*args, **kwargs)

    def get_store_url(self):
        return self.api_url.rstrip('/')

    def get_admin_url(self):
        return f'{self.get_store_url()}/administration'

    def get_admin_order_details(self, order_id):
        return f'{self.get_admin_url()}/v2/index.php?controller=AdminOrders&id_order={order_id}&vieworder'

    def get_api_url(self, path):
        return '{}/api/{}'.format(self.get_store_url(), path.lstrip('/'))

    def get_short_hash(self):
        return self.store_hash[:8] if self.store_hash else ''

    def pusher_channel(self):
        return 'gkart_{}'.format(self.get_short_hash())

    def pusher_trigger(self, event, data):
        if not settings.PUSHER_APP_ID:
            return

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger(self.pusher_channel(), event, data)


class GrooveKartProduct(models.Model):
    class Meta:
        verbose_name = 'GrooveKart Product'
        ordering = ['-created_at']

    store = models.ForeignKey('GrooveKartStore', related_name='products', null=True)
    user = models.ForeignKey(User)

    data = models.TextField(default='{}', blank=True)
    notes = models.TextField(null=True, blank=True)

    title = models.CharField(max_length=300, blank=True, db_index=True)
    price = models.FloatField(blank=True, null=True, db_index=True)
    tags = models.TextField(blank=True, default='', db_index=True)
    product_type = models.CharField(max_length=300, blank=True, default='', db_index=True)

    source_id = models.BigIntegerField(default=0, null=True, blank=True, db_index=True, verbose_name='GrooveKartSupplier Product ID')
    source_slug = models.CharField(max_length=300, blank=True, default='')
    default_supplier = models.ForeignKey('GrooveKartSupplier', on_delete=models.SET_NULL, null=True, blank=True)

    config = models.TextField(null=True, blank=True)
    variants_map = models.TextField(default='', blank=True)
    supplier_map = models.TextField(default='', null=True, blank=True)
    shipping_map = models.TextField(default='', null=True, blank=True)
    mapping_config = models.TextField(null=True, blank=True)

    parent_product = models.ForeignKey('GrooveKartProduct', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Duplicate of product')

    monitor_id = models.IntegerField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        try:
            title = self.title
            if len(title) > 79:
                return '{}...'.format(textwrap.wrap(title, width=79)[0])
            elif title:
                return title
            else:
                return '<GrooveKartProduct: {}'.format(self.id)
        except:
            return '<GrooveKartProduct: {}'.format(self.id)

    @staticmethod
    def get_variant_options(variant):
        return variant['description'].split(' | ')

    @property
    def parsed(self):
        try:
            return json.loads(self.data)
        except:
            return {}

    @property
    def groovekart_url(self):
        if self.is_connected:
            admin_url = self.store.get_admin_url().rstrip('/')
            return '{}/v2/index.php/product/form/{}'.format(admin_url, self.source_id)

    @property
    def is_connected(self):
        return bool(self.source_id)

    @property
    def has_supplier(self):
        try:
            return self.default_supplier is not None
        except:
            return False

    def get_gkart_id(self):
        return self.source_id if self.store else None

    def save(self, *args, **kwargs):
        data = json.loads(self.data)

        self.title = data.get('title', '')
        self.tags = safe_str(data.get('tags', ''))[:1024]
        self.product_type = safe_str(data.get('type', ''))[:254]

        try:
            self.price = '%.02f' % float(data['price'])
        except:
            self.price = 0.0

        super().save(*args, **kwargs)

    def sync(self):
        product_data = self.retrieve()
        # assert False, json.dumps(product_data, indent=4)
        product_variants = product_data.get('variants', [])
        self.update_data({'title': product_data.get('title', product_data.get('product_title'))})
        self.update_data({'price': f'{float(product_data["price"]):,.2f}'})
        self.update_data({'compare_at_price': f'{float(product_data["compare_default_price"]):,.2f}'})
        self.update_data({'weight': product_data['weight']})
        self.update_data({'sku': product_data['sku']})
        self.update_data({'description': product_data['description']})
        self.update_data({'cover_image': product_data.get('cover_image', '')})
        self.update_data({'tags': product_data.get('tags', '')})
        self.update_data({'variants': self.sync_variants(product_variants)})
        self.update_data({'images': {i.get('id'): i.get('url') for i in product_data.get('images', [])}})
        self.save()

        return self.parsed

    def sync_variants(self, product_variants):
        variants = []

        for product_variant in product_variants:
            variant_id = dict_val(product_variant, ['id_product_attribute', 'id_product_variant'])
            variant_name = dict_val(product_variant, ['attribute_name', 'variant_name'])
            product_variant['price'] = "%.2f" % float(product_variant['price'])
            product_variant['compare_at_price'] = "%.2f" % float(product_variant['compare_price'])
            for variant in variants:
                if variant_id == variant['id']:
                    variant['description'] += ' | {}'.format(variant_name)
                    break
            else:
                product_variant['id'] = variant_id
                product_variant['description'] = variant_name
                if product_variant.get('image'):
                    src = product_variant['image']['url']
                    m = re.search(r'\?', src)
                    src = src[:m.span()[0]] if m else src
                    results = re.findall(r'(\.jpg)|(\.jpeg)|(\.png)', src)
                    extension = results.pop()[0] if results else ''
                    file = src.rstrip(extension)
                    product_variant['image']['src'] = "{}-small_default{}".format(file, extension)
                variants.append(product_variant)

        return variants

    def retrieve(self):
        # TODO: Change URL to products.json when it start returning the images
        endpoint = self.store.get_api_url('search_products.json')
        json_data = {'ids': self.source_id}
        r = self.store.request.post(endpoint, json=json_data)
        r.raise_for_status()

        return r.json()['products']['0']

    def get_config(self):
        try:
            return json.loads(self.config)
        except:
            return {}

    def update_data(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        try:
            product_data = json.loads(self.data)
        except:
            product_data = {}

        product_data.update(data)

        self.data = json.dumps(product_data)

    def get_suppliers(self):
        return self.groovekartsupplier_set.all().order_by('-is_default')

    def set_default_supplier(self, supplier, commit=False):
        self.default_supplier = supplier

        if commit:
            self.save()

        self.get_suppliers().update(is_default=False)

        supplier.is_default = True
        supplier.save()

    def get_mapping_config(self):
        try:
            return json.loads(self.mapping_config)
        except:
            return {}

    def set_mapping_config(self, config):
        if type(config) is not str:
            config = json.dumps(config)

        self.mapping_config = config
        self.save()

    def get_variant_mapping(self, name=None, default=None, for_extension=False, supplier=None, mapping_supplier=False):
        mapping = {}

        if supplier is None:
            if mapping_supplier:
                supplier = self.get_supplier_for_variant(name)
            else:
                supplier = self.default_supplier

        try:
            if supplier and supplier.variants_map:
                mapping = json.loads(supplier.variants_map)
            elif self.variants_map:
                mapping = json.loads(self.variants_map)
            else:
                mapping = {}
        except:
            mapping = {}

        if name:
            mapping = mapping.get(str(name), default)

        try:
            mapping = json.loads(mapping)
        except:
            pass

        if type(mapping) is int:
            mapping = str(mapping)

        if for_extension and mapping:
            if name:
                if type(mapping) is str:
                    mapping = mapping.split(',')
            else:
                for k, v in list(mapping.items()):
                    m = str(v) if type(v) is int else v

                    try:
                        m = json.loads(v)
                    except:
                        if type(v) is str:
                            m = v.split(',')

                    mapping[k] = m

        return mapping

    def set_variant_mapping(self, mapping, supplier=None, update=False, commit=True):
        if supplier is None:
            supplier = self.default_supplier

        if update:
            try:
                current = json.loads(supplier.variants_map)
            except:
                current = {}

            for k, v in list(mapping.items()):
                current[k] = v

            mapping = current

        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        if supplier:
            supplier.variants_map = mapping
            if commit:
                supplier.save()
        else:
            self.variants_map = mapping
            if commit:
                self.save()

    def get_suppliers_mapping(self, name=None, default=None):
        mapping = {}
        try:
            if self.supplier_map:
                mapping = json.loads(self.supplier_map)
            else:
                mapping = {}
        except:
            mapping = {}

        if name:
            mapping = mapping.get(str(name), default)

        try:
            mapping = json.loads(mapping)
        except:
            pass

        if type(mapping) is int:
            mapping = str(mapping)

        return mapping

    def set_suppliers_mapping(self, mapping, commit=True):
        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.supplier_map = mapping

        if commit:
            self.save()

    def get_shipping_mapping(self, supplier=None, variant=None, default=None):
        mapping = {}
        try:
            if self.shipping_map:
                mapping = json.loads(self.shipping_map)
            else:
                mapping = {}
        except:
            mapping = {}

        if supplier and variant:
            mapping = mapping.get('{}_{}'.format(supplier, variant), default)

        try:
            mapping = json.loads(mapping)
        except:
            pass

        if type(mapping) is int:
            mapping = str(mapping)

        return mapping

    def set_shipping_mapping(self, mapping, update=True, commit=True):
        if update:
            try:
                current = json.loads(self.shipping_map)
            except:
                current = {}

            for k, v in list(mapping.items()):
                current[k] = v

            mapping = current

        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.shipping_map = mapping

        if commit:
            self.save()

    def get_original_info(self):
        if self.has_supplier:
            url = self.default_supplier.product_url

            try:
                domain = urlparse(url).hostname
            except:
                domain = None

            if domain is None:
                return domain

            for i in ['com', 'co.uk', 'org', 'net']:
                domain = domain.replace('.%s' % i, '')

            domain = domain.split('.')[-1]

            return {
                'domain': domain,
                'source': domain.title(),
                'url': url
            }

    def get_all_variants_mapping(self):
        all_mapping = {}

        product = self.sync()
        if not product:
            return None

        for supplier in self.get_suppliers():
            variants_map = self.get_variant_mapping(supplier=supplier)

            seen_variants = []
            for i, v in enumerate(product['variants']):
                mapped = variants_map.get(str(v['id']))
                if mapped:
                    options = mapped
                else:
                    options = GrooveKartProduct.get_variant_options(v)
                    options = [{'title': a} for a in options]

                try:
                    if type(options) not in [list, dict]:
                        options = json.loads(options)

                        if type(options) is int:
                            options = str(options)
                except:
                    pass

                variants_map[str(v['id'])] = options
                seen_variants.append(str(v['id']))

            for k in list(variants_map.keys()):
                if k not in seen_variants:
                    del variants_map[k]

            all_mapping[str(supplier.id)] = variants_map

        return all_mapping


class GrooveKartSupplier(models.Model):
    store = models.ForeignKey('GrooveKartStore', null=True, related_name='suppliers')
    product = models.ForeignKey('GrooveKartProduct')

    product_url = models.CharField(max_length=512, null=True, blank=True)
    supplier_name = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    supplier_url = models.CharField(max_length=512, null=True, blank=True)
    shipping_method = models.CharField(max_length=512, null=True, blank=True)
    variants_map = models.TextField(null=True, blank=True)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.supplier_name:
            return self.supplier_name
        elif self.supplier_url:
            return self.supplier_url
        else:
            return '<GrooveKartSupplier: {}>'.format(self.id)

    def get_source_id(self):
        try:
            if self.is_aliexpress:
                return int(re.findall('[/_]([0-9]+).html', self.product_url)[0])
            elif self.is_ebay:
                return int(re.findall(r'ebay\.[^/]+\/itm\/(?:[^/]+\/)?([0-9]+)', self.product_url)[0])
        except:
            return None

    def get_store_id(self):
        try:
            if self.is_aliexpress:
                return int(re.findall('/([0-9]+)', self.supplier_url).pop())
        except:
            return None

    def short_product_url(self):
        source_id = self.get_source_id()
        if source_id:
            if self.is_aliexpress:
                return 'https://www.aliexpress.com/item//{}.html'.format(source_id)
            if self.is_ebay:
                return 'https://www.ebay.com/itm/{}'.format(source_id)

        return self.product_url

    def support_auto_fulfill(self):
        """
        Return True if this supplier support auto fulfill using the extension
        Currently Aliexpress and eBay (US) support that
        """

        return self.is_aliexpress or self.is_ebay_us

    def get_name(self):
        if self.supplier_name and self.supplier_name.strip():
            name = self.supplier_name.strip()
        else:
            supplier_idx = 1
            for i in self.product.get_suppliers():
                if self.id == i.id:
                    break
                else:
                    supplier_idx += 1

            name = 'Supplier {}#{}'.format(self.supplier_type(), supplier_idx)

        return name

    def supplier_type(self):
        try:
            return get_domain(self.product_url)
        except:
            return ''

    @property
    def is_aliexpress(self):
        return self.supplier_type() == 'aliexpress'

    @property
    def is_ebay(self):
        return self.supplier_type() == 'ebay'

    @property
    def is_ebay_us(self):
        try:
            return 'ebay.com' in get_domain(self.product_url, full=True)
        except:
            return False

    def save(self, *args, **kwargs):
        if self.is_default:
            try:
                if not settings.DEBUG:
                    monitor_product(self.product)
            except:
                pass

        super(GrooveKartSupplier, self).save(*args, **kwargs)


class GrooveKartBoard(models.Model):
    class Meta:
        verbose_name = "GrooveKart Board"
        verbose_name_plural = "GrooveKart Boards"

    user = models.ForeignKey(User)
    title = models.CharField(max_length=512)
    products = models.ManyToManyField('GrooveKartProduct', blank=True, related_name='boards')
    config = models.CharField(max_length=512, blank=True, default='')
    favorite = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return self.title

    def saved_count(self):
        products = self.products.filter(Q(store__is_active=True) | Q(store__isnull=True))
        products = products.filter(source_id=0)

        return products.count()

    def connected_count(self):
        return self.products.filter(store__is_active=True).exclude(source_id=0).count()


class GrooveKartOrderTrack(models.Model):
    class Meta:
        ordering = ['-created_at']
        index_together = ['store', 'order_id', 'line_id']

    user = models.ForeignKey(User)
    store = models.ForeignKey('GrooveKartStore', null=True)
    order_id = models.BigIntegerField()
    line_id = models.BigIntegerField()
    groovekart_status = models.CharField(max_length=128, blank=True, null=True, default='', verbose_name="GrooveKart Fulfillment Status")

    source_id = models.CharField(max_length=512, blank=True, default='', db_index=True, verbose_name="Source Order ID")
    source_status = models.CharField(max_length=128, blank=True, default='', verbose_name="Source Order Status")
    source_tracking = models.CharField(max_length=128, blank=True, default='', verbose_name="Source Tracking Number")
    source_status_details = models.CharField(max_length=512, blank=True, null=True, verbose_name="Source Status Details")
    source_type = models.CharField(max_length=512, blank=True, null=True, verbose_name="Source Type")

    hidden = models.BooleanField(default=False)
    seen = models.BooleanField(default=False, verbose_name='User viewed the changes')
    auto_fulfilled = models.BooleanField(default=False, verbose_name='Automatically fulfilled')
    check_count = models.IntegerField(default=0)

    data = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')
    status_updated_at = models.DateTimeField(auto_now_add=True, verbose_name='Last Status Update')

    def save(self, *args, **kwargs):
        try:
            self.source_status_details = json.loads(self.data)['aliexpress']['end_reason']
        except:
            pass

        super(GrooveKartOrderTrack, self).save(*args, **kwargs)

    def encoded(self):
        return base64_encode(json.dumps(self.data))

    def get_tracking_link(self):
        aftership_domain = 'http://track.aftership.com/{{tracking_number}}'

        if type(self.user.get_config('aftership_domain')) is dict:
            aftership_domain = self.user.get_config('aftership_domain').get(str(self.store_id), aftership_domain)

            if '{{tracking_number}}' not in aftership_domain:
                aftership_domain = "http://{}.aftership.com/{{{{tracking_number}}}}".format(aftership_domain)
            elif not aftership_domain.startswith('http'):
                aftership_domain = 'http://{}'.format(re.sub('^([:/]*)', r'', aftership_domain))

        return aftership_domain.replace('{{tracking_number}}', self.source_tracking)

    def get_source_url(self):
        if self.source_id:
            if self.source_type == 'ebay':
                return 'https://vod.ebay.com/vod/FetchOrderDetails?purchaseOrderId={}'.format(self.source_id)
            else:
                return 'http://trade.aliexpress.com/order_detail.htm?orderId={}'.format(self.source_id)
        else:
            return None

    def get_source_status(self):
        status_map = {
            # Aliexpress
            "PLACE_ORDER_SUCCESS": "Awaiting Payment",
            "IN_CANCEL": "Awaiting Cancellation",
            "WAIT_SELLER_SEND_GOODS": "Awaiting Shipment",
            "SELLER_PART_SEND_GOODS": "Partial Shipment",
            "WAIT_BUYER_ACCEPT_GOODS": "Awaiting delivery",
            "WAIT_GROUP_SUCCESS": "Pending operation success",
            "FINISH": "Order Completed",
            "IN_ISSUE": "Dispute Orders",
            "IN_FROZEN": "Frozen Orders",
            "WAIT_SELLER_EXAMINE_MONEY": "Payment not yet confirmed",
            "RISK_CONTROL": "Payment being verified",
            "IN_PRESELL_PROMOTION": "Promotion is on",
            "FUND_PROCESSING": "Fund Processing",

            # eBay
            "BUYER_NO_SHOW": "Pickup cancelled buyer no show",
            "BUYER_REJECTED": "Pickup cancelled buyer rejected",
            "DELIVERED": "Delivered",
            "DIRECT_DEBIT": "Direct Debit",
            "EXTERNAL_WALLET": "Processed by PayPal",
            "IN_TRANSIT": "In transit",
            "MANIFEST": "Shipping Info Received",
            "NO_PICKUP_INSTRUCTIONS_AVAILABLE": "No pickup instruction available",
            "NOT_PAID": "Not Paid",
            "NOT_SHIPPED": "Item is not shipped",
            "SHIPPED": "Shipped",
            "OUT_OF_STOCK": "Out of stock",
            "PENDING_MERCHANT_CONFIRMATION": "Order is being prepared",
            "PICKED_UP": "Picked up",
            "PICKUP_CANCELLED_BUYER_NO_SHOW": "Pickup cancelled buyer no show",
            "PICKUP_CANCELLED_BUYER_REJECTED": "Pickup cancelled buyer rejected",
            "PICKUP_CANCELLED_OUT_OF_STOCK": "Out of stock",
            "READY_FOR_PICKUP": "Ready for pickup",
            "SHIPPING_INFO_RECEIVED": "Shipping info received"
        }

        return status_map.get(self.source_status)

    get_source_status.admin_order_field = 'source_status'

    def __str__(self):
        return '{} | {}'.format(self.order_id, self.line_id)