import textwrap
import json
import re
from urllib.parse import urlencode

from pusher import Pusher
from woocommerce import API

from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.utils.crypto import get_random_string
from django.urls import reverse

from shopified_core.utils import get_domain, safe_str, base64_encode
from shopified_core.decorators import add_to_class


@add_to_class(User, 'get_woo_boards')
def user_get_woo_boards(self):
    if self.is_subuser:
        return self.profile.subuser_parent.get_woo_boards()
    else:
        return self.wooboard_set.all().order_by('title')


class WooStore(models.Model):
    class Meta:
        verbose_name = 'WooCommerce Store'

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=300, blank=True, default='')
    api_url = models.CharField(max_length=512)
    api_key = models.CharField(max_length=300)
    api_password = models.CharField(max_length=300)

    is_active = models.BooleanField(default=True)
    store_hash = models.CharField(default='', max_length=50, editable=False)

    list_index = models.IntegerField(default=0)
    auto_fulfill = models.CharField(max_length=50, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_wcapi(self, timeout=30):
        return API(
            url=self.api_url,
            consumer_key=self.api_key,
            consumer_secret=self.api_password,
            wp_api=True,
            version='wc/v2',
            verify_ssl=False,
            query_string_auth=True,
            timeout=timeout)

    wcapi = property(get_wcapi)

    def save(self, *args, **kwargs):
        if not self.store_hash:
            self.store_hash = get_random_string(32, 'abcdef0123456789')

        try:
            self.auto_fulfill = self.user.get_config('auto_shopify_fulfill', '')
        except User.DoesNotExist:
            pass

        super(WooStore, self).save(*args, **kwargs)

    def get_store_url(self):
        return self.api_url.rstrip('/')

    def get_admin_url(self):
        return self.get_store_url() + '/wp-admin'

    def get_authorize_url(self, params):
        return '{}/wc-auth/v1/authorize?{}'.format(self.get_store_url(), urlencode(params))

    def get_suppliers(self):
        return self.woosupplier_set.all().order_by('-is_default')

    def set_default_supplier(self, supplier, commit=False):
        self.default_supplier = supplier

        if commit:
            self.save()

        self.get_suppliers().update(is_default=False)

        supplier.is_default = True
        supplier.save()

    def connected_count(self):
        return self.products.exclude(source_id=0).count()

    def saved_count(self):
        return self.products.filter(source_id=0).count()

    def get_short_hash(self):
        return self.store_hash[:8] if self.store_hash else ''

    def pusher_channel(self):
        return 'woo_{}'.format(self.get_short_hash())

    def pusher_trigger(self, event, data):
        if not settings.PUSHER_APP_ID:
            return

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger(self.pusher_channel(), event, data)


class WooProduct(models.Model):
    class Meta:
        verbose_name = 'WooCommerce Product'
        ordering = ['-created_at']

    store = models.ForeignKey('WooStore', related_name='products', null=True, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    data = models.TextField(default='{}', blank=True)
    notes = models.TextField(null=True, blank=True)

    title = models.CharField(max_length=300, blank=True, db_index=True)
    price = models.FloatField(blank=True, null=True, db_index=True)
    tags = models.TextField(blank=True, default='', db_index=True)
    product_type = models.CharField(max_length=300, blank=True, default='', db_index=True)

    source_id = models.BigIntegerField(default=0, null=True, blank=True, db_index=True, verbose_name='WooCommerce Product ID')
    default_supplier = models.ForeignKey('WooSupplier', on_delete=models.SET_NULL, null=True, blank=True)

    variants_map = models.TextField(default='', blank=True)
    supplier_map = models.TextField(default='', null=True, blank=True)
    shipping_map = models.TextField(default='', null=True, blank=True)
    mapping_config = models.TextField(null=True, blank=True)

    parent_product = models.ForeignKey('WooProduct', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Duplicate of product')

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
                return '<WooProduct: {}>'.format(self.id)
        except:
            return '<WooProduct: {}>'.format(self.id)

    @property
    def parsed(self):
        try:
            return json.loads(self.data)
        except:
            return {}

    @property
    def woocommerce_url(self):
        if self.is_connected:
            admin_url = self.store.get_admin_url().rstrip('/')
            return '{}/post.php?post={}&action=edit'.format(admin_url, self.source_id)

        return None

    @property
    def variant_edit(self):
        if self.is_connected:
            return reverse('woo:variants_edit', args=(self.store.id, self.source_id))

        return None

    @property
    def is_connected(self):
        return bool(self.source_id)

    @property
    def boards(self):
        return self.wooboard_set

    def has_supplier(self):
        try:
            return self.default_supplier is not None
        except:
            return False

    def save(self, *args, **kwargs):
        data = json.loads(self.data)

        self.title = data.get('title', '')
        self.tags = safe_str(data.get('tags', ''))[:1024]
        self.product_type = safe_str(data.get('type', ''))[:254]

        try:
            self.price = '%.02f' % float(data['price'])
        except:
            self.price = 0.0

        super(WooProduct, self).save(*args, **kwargs)

    def update_data(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        try:
            product_data = json.loads(self.data)
        except:
            product_data = {}

        product_data.update(data)

        self.data = json.dumps(product_data)

    def retrieve(self):
        """ Retrieve product from WooCommerce API """
        if not self.source_id:
            return None

        r = self.store.wcapi.get('products/{}'.format(self.source_id))
        r.raise_for_status()

        product = r.json()
        product['variants'] = self.retrieve_variants()

        return product

    def retrieve_variants(self):
        variants = []
        page = 1
        while page:
            params = urlencode({'page': page, 'per_page': 100})
            path = 'products/{}/variations?{}'.format(self.source_id, params)
            r = self.store.wcapi.get(path)
            r.raise_for_status()
            fetched_variants = r.json()
            variants.extend(fetched_variants)
            has_next = 'rel="next"' in r.headers.get('link', '')
            page = page + 1 if has_next else 0

        for variant in variants:
            attributes = variant.get('attributes', [])
            variant['variant'] = [option['option'] for option in attributes]

        if not variants:
            variants = [{'variant': ['Default Title'], 'id': -1}]

        return variants

    def sync(self):
        if not self.source_id:
            return None

        product_data = self.retrieve()
        product_data['tags'] = self.merge_tags(product_data)
        product_data['images'] = [img['src'] for img in product_data.get('images', [])]
        product_data['title'] = product_data.pop('name')
        product_data['product_type'] = product_data.pop('type')
        product_data['compare_at_price'] = product_data.pop('regular_price')
        product_data['published'] = product_data['status'] == 'publish'

        self.update_data(product_data)
        self.save()

        product = json.loads(self.data)

        return product

    def merge_tags(self, product_data):
        woocommerce_tags = [tag['name'] for tag in product_data.get('tags', [])]
        dropified_tags = self.tags.split(',')

        return ','.join(set(dropified_tags + woocommerce_tags))

    def get_suppliers(self):
        return self.woosupplier_set.all().order_by('-is_default')

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

    def get_supplier_for_variant(self, variant_id):
        """
            Return the mapped Supplier for the given variant_id
            or the default one if mapping is not set/found
        """

        config = self.get_mapping_config()
        mapping = self.get_suppliers_mapping(name=variant_id)

        if not variant_id or not mapping or config.get('supplier') == 'default':
            return self.default_supplier

        try:
            return self.woosupplier_set.get(id=mapping['supplier'])
        except:
            return self.default_supplier

    def get_variant_mapping(self, name=None, default=None, for_extension=False, supplier=None, mapping_supplier=False):
        name = -1 if name == 0 else name
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

    def get_shipping_for_variant(self, supplier_id, variant_id, country_code):
        """ Return Shipping Method for the given variant_id and country_code """
        variant_id = -1 if variant_id == 0 else variant_id
        mapping = self.get_shipping_mapping(supplier=supplier_id, variant=variant_id)

        if variant_id and country_code and mapping and type(mapping) is list:
            for method in mapping:
                if country_code == method.get('country'):
                    short_name = method.get('method_name').split(' ')
                    if len(short_name) > 1 and short_name[1].lower() in ['post', 'seller\'s', 'aliexpress']:
                        method['method_short'] = ' '.join(short_name[:2])
                    else:
                        method['method_short'] = short_name[0]

                    if method['country'] == 'GB':
                        method['country'] = 'UK'

                    return method

        return None

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
                    options = v['variant']

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


class WooSupplier(models.Model):
    store = models.ForeignKey('WooStore', null=True, related_name='suppliers', on_delete=models.CASCADE)
    product = models.ForeignKey('WooProduct', on_delete=models.CASCADE)

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
            return '<WooSupplier: {}>'.format(self.id)

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


class WooOrderTrack(models.Model):
    class Meta:
        ordering = ['-created_at']
        index_together = ['store', 'order_id', 'line_id']

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey(WooStore, null=True, on_delete=models.CASCADE)
    order_id = models.BigIntegerField()
    line_id = models.BigIntegerField()
    product_id = models.BigIntegerField()
    woocommerce_status = models.CharField(max_length=128, blank=True, null=True, default='', verbose_name="WooCommerce Fulfillment Status")

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

        super(WooOrderTrack, self).save(*args, **kwargs)

    def encoded(self):
        return base64_encode(json.dumps(self.data))

    def get_tracking_link(self):
        if self.user.id in [49354]:
            aftership_domain = 'http://17track.net/?nums={{tracking_number}}'
        else:
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

    def get_source_status_details(self):
        ALIEXPRESS_REJECTED_STATUS = {
            "buyer_pay_timeout": "Order Payment Timeout",
            "risk_reject_closed": "Rejected By Risk Control",
            "buyer_accept_goods_timeout": "Buyer Accept Goods Timeout",
            "buyer_cancel_notpay_order": "Buyer Cancel or Doesn't Pay Order",
            "cancel_order_close_trade": "Cancel Order Close Trade",
            "seller_send_goods_timeout": "Seller Send Goods Timeout",
            "buyer_cancel_order_in_risk": "Buyer Cancel Order In Risk",
            "buyer_accept_goods": "Buyer Accept Goods",
            "seller_accept_issue_no_goods_return": "Seller Accept Issue No Goods Return",
            "seller_response_issue_timeout": "Seller Response Issue Timeout",
        }

        if self.source_status_details and ',' in self.source_status_details:
            source_status_details = []
            for i in self.source_status_details.split(','):
                source_status_details.append(ALIEXPRESS_REJECTED_STATUS.get(safe_str(i).lower()))

            return ', '.join(set(source_status_details))
        else:
            return ALIEXPRESS_REJECTED_STATUS.get(safe_str(self.source_status_details).lower())

    def __str__(self):
        return '{} | {}'.format(self.order_id, self.line_id)


class WooBoard(models.Model):
    class Meta:
        verbose_name = "WooCommerce Board"
        verbose_name_plural = "WooCommerce Boards"

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=512)
    products = models.ManyToManyField('WooProduct', blank=True)
    config = models.CharField(max_length=512, blank=True, default='')
    favorite = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return self.title

    def saved_count(self):
        return self.products.filter(store__is_active=True, source_id=0).count()

    def connected_count(self):
        return self.products.filter(store__is_active=True).exclude(source_id=0).count()


class WooUserUpload(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(WooProduct, null=True, on_delete=models.CASCADE)
    url = models.CharField(max_length=512, blank=True, default='', verbose_name="Upload file URL")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return self.url.replace('%2F', '/').split('/')[-1]
