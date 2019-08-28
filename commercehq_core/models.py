from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string

import re
import simplejson as json
from urllib.parse import urlparse

import requests
from pusher import Pusher

from shopified_core.utils import (
    hash_url_filename,
    get_domain,
    safe_str,
    base64_encode,
)
from shopified_core.decorators import add_to_class
from shopified_core.models import StoreBase, ProductBase, SupplierBase, BoardBase, OrderTrackBase
from product_alerts.utils import monitor_product


@add_to_class(User, 'get_chq_boards')
def user_get_chq_boards(self):
    if self.is_subuser:
        return self.profile.subuser_parent.get_chq_boards()
    else:
        return self.commercehqboard_set.all().order_by('title')


class CommerceHQStore(StoreBase):
    class Meta(StoreBase.Meta):
        verbose_name = 'CHQ Store'
        ordering = ['-created_at']

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=300, blank=True, default='')
    api_url = models.CharField(max_length=512)
    api_key = models.CharField(max_length=300)
    api_password = models.CharField(max_length=300)

    is_active = models.BooleanField(default=True)
    store_hash = models.CharField(unique=True, default='', max_length=50, editable=False)

    auto_fulfill = models.CharField(max_length=50, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.store_hash:
            self.store_hash = get_random_string(32, 'abcdef0123456789')

        try:
            self.auto_fulfill = self.user.get_config('auto_shopify_fulfill', 'enable')
        except User.DoesNotExist:
            pass

        super(CommerceHQStore, self).save(*args, **kwargs)

    def get_api_url(self, *args, **kwargs):
        """
        Get CommerceHQ Store API Url

        :param args: one or more pages to add to the url
        :param api: Return the API version of the url if true, otherwise return Admin url
        """

        url = re.findall(r'([^/.]+\.commercehq(?:dev|testing)?\.com)', self.api_url).pop()

        args = '/'.join([str(i) for i in args]).lstrip('/')
        if kwargs.get('api', True):
            if not args.startswith('api'):
                args = 'api/v1/{}'.format(args).rstrip('/')
        else:
            if not args.startswith('admin'):
                args = 'admin/{}'.format(args).rstrip('/')

        url = 'https://{}/{}'.format(url, args.lstrip('/'))

        return url

    def get_admin_url(self, *args):
        return self.get_api_url(*args, api=False)

    def get_store_url(self, *args):
        url = re.findall(r'([^/.]+\.commercehq(?:dev|testing)?\.com)', self.api_url).pop()
        if len(args):
            url = url + '/' + '/'.join([str(i) for i in args]).lstrip('/')

        return 'https://{}'.format(url)

    @property
    def request(self):
        s = requests.Session()
        s.auth = (self.api_key, self.api_password)
        return s

    def connected_count(self):
        return self.products.exclude(source_id=0).count()

    def saved_count(self):
        return self.products.filter(source_id=0).count()

    def get_short_hash(self):
        return self.store_hash[:8] if self.store_hash else ''

    def pusher_channel(self):
        return 'chq_{}'.format(self.get_short_hash())

    def pusher_trigger(self, event, data):
        if not settings.PUSHER_APP_ID:
            return

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger(self.pusher_channel(), event, data)


class CommerceHQProduct(ProductBase):
    class Meta(ProductBase.Meta):
        verbose_name = 'CHQ Product'
        ordering = ['-created_at']

    store = models.ForeignKey('CommerceHQStore', related_name='products', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    data = models.TextField(default='{}', blank=True)
    notes = models.TextField(null=True, blank=True)

    title = models.CharField(max_length=300, db_index=True)
    price = models.FloatField(blank=True, null=True, db_index=True)
    product_type = models.CharField(max_length=300, db_index=True)
    tags = models.TextField(blank=True, default='', db_index=True)
    is_multi = models.BooleanField(default=False)
    parent_product = models.ForeignKey('CommerceHQProduct', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Duplicate of product')

    config = models.TextField(null=True, blank=True)
    variants_map = models.TextField(default='', blank=True)
    supplier_map = models.TextField(default='', null=True, blank=True)
    shipping_map = models.TextField(default='', null=True, blank=True)
    bundle_map = models.TextField(null=True, blank=True)
    mapping_config = models.TextField(null=True, blank=True)

    parent_product = models.ForeignKey(
        'CommerceHQProduct', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Dupliacte of product')

    source_id = models.BigIntegerField(default=0, null=True, blank=True, db_index=True, verbose_name='CommerceHQ Product ID')
    default_supplier = models.ForeignKey('CommerceHQSupplier', on_delete=models.SET_NULL, null=True, blank=True)

    monitor_id = models.IntegerField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'<CommerceHQProduct: {self.id}'

    def save(self, *args, **kwargs):
        data = json.loads(self.data)

        self.title = data.get('title', '')
        self.tag = safe_str(data.get('tags', ''))[:1024]
        self.product_type = safe_str(data.get('type', ''))[:254]

        try:
            self.price = '%.02f' % float(data['price'])
        except:
            self.price = 0.0

        super(CommerceHQProduct, self).save(*args, **kwargs)

    @property
    def parsed(self):
        try:
            return json.loads(self.data)
        except:
            return {}

    @property
    def commercehq_url(self):
        if self.is_connected:
            return '{}?id={}'.format(self.store.get_admin_url('admin/products/view'), self.source_id)
        else:
            return None

    @property
    def is_connected(self):
        return bool(self.get_chq_id())

    @property
    def boards(self):
        return self.commercehqboard_set

    def have_supplier(self):
        try:
            return self.default_supplier is not None
        except:
            return False

    def get_chq_id(self):
        return self.source_id if self.store else None

    def get_product(self):
        try:
            return json.loads(self.data)['title']
        except:
            return None

    def update_data(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        try:
            product_data = json.loads(self.data)
        except:
            product_data = {}

        product_data.update(data)

        self.data = json.dumps(product_data)

    def set_default_supplier(self, supplier, commit=False):
        self.default_supplier = supplier

        if commit:
            self.save()

        self.get_suppliers().update(is_default=False)

        supplier.is_default = True
        supplier.save()

    def get_suppliers(self):
        return self.commercehqsupplier_set.all().order_by('-is_default')

    def retrieve(self):
        """ Retrieve product from CommerceHQ API """

        if not self.source_id:
            return None

        rep = self.store.request.get(
            url=self.store.get_api_url('products', self.source_id),
            params={
                'expand': 'variants,options,images,textareas'
            }
        )

        if rep.ok:
            return rep.json()

    def sync(self):
        product = self.retrieve()
        if not product:
            return None

        product['tags'] = ','.join(product['tags']) if type(product['tags']) is list else ''

        for idx, img in enumerate(product['images']):
            product['images'][idx] = img['path']

        for i in product['textareas']:
            if i['name'] == 'Description':
                product['description'] = i['text']

        if not product['is_multi']:
            product['price'] = product.get('price')
            product['compare_at_price'] = product.get('compare_price')
        else:
            prices = []
            for v in product['variants']:
                prices.append(v['price'])

            if len(set(prices)) == 1:
                product['price'] = prices[0]
            else:
                product['price_range'] = [min(prices), max(prices)]

        product['weight'] = product['shipping_weight']
        product['published'] = not product['is_draft']
        product['textareas'] = []
        self.update_data(product)
        self.save()

        product = json.loads(self.data)

        if not product['is_multi']:
            # CommerceHQ doesn't set this values when product is not a multi variants product
            product['options'] = []
            product['variants'] = [{
                "id": -1,
                "variant": ["Default"],
                "images": product['images']
            }]

        return product

    def get_config(self):
        try:
            return json.loads(self.config)
        except:
            return {}

    def get_real_variant_id(self, variant_id):
        """
        Used to get current variant id from previously delete variant id
        """

        config = self.get_config()
        if config.get('real_variant_map'):
            return config.get('real_variant_map').get(str(variant_id), variant_id)

        return variant_id

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

    def set_suppliers_mapping(self, mapping, commit=True):
        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.supplier_map = mapping

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

    def get_bundle_mapping(self, variant=None, default=[]):
        try:
            bundle_map = json.loads(self.bundle_map)
        except:
            bundle_map = {}

        if variant:
            return bundle_map.get(str(variant), default)
        else:
            return bundle_map

    def set_bundle_mapping(self, mapping):
        bundle_map = self.get_bundle_mapping()
        bundle_map.update(mapping)

        self.bundle_map = json.dumps(bundle_map)

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
            return self.commercehqsupplier_set.get(id=mapping['supplier'])
        except:
            return self.default_supplier

    def get_shipping_for_variant(self, supplier_id, variant_id, country_code):
        """ Return Shipping Method for the given variant_id and country_code """
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

    def get_common_images(self):
        common_images = set()
        image_urls = self.parsed.get('images', [])

        if not self.source_id:
            hashed_variant_images = list(self.parsed.get('variants_images', {}).keys())

            for image_url in image_urls:
                if hash_url_filename(image_url) not in hashed_variant_images:
                    common_images.add(image_url)
        else:
            variant_primary_images = []
            variants = self.parsed.get('variants', [])

            for variant in variants:
                images = variant.get('images', [])

                for i, image in enumerate(images):
                    if i == 0:
                        variant_primary_images.append(image['path'])
                    else:
                        common_images.add(image['path'])

            if len(set(variant_primary_images)) == 1:
                # variants are using one common image
                common_images.update(set(image_urls) | set(variant_primary_images))
            else:
                common_images.update(set(image_urls) - set(variant_primary_images))

        return list(common_images)

    def get_image(self):
        images = self.parsed.get('images', [])

        if images:
            return images[0]

        common_images = self.get_common_images()

        if common_images:
            return common_images[0]

        variants = self.parsed.get('variants', [])
        variant_images = []
        for variant in variants:
            for image in variant.get('images', []):
                variant_images.append(image.get('path'))

        return variant_images[0] if variant_images else ''

    def get_original_info(self):
        if self.have_supplier():
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


class CommerceHQSupplier(SupplierBase):
    store = models.ForeignKey(CommerceHQStore, related_name='suppliers', on_delete=models.CASCADE)
    product = models.ForeignKey(CommerceHQProduct, on_delete=models.CASCADE)

    product_url = models.CharField(max_length=512, null=True, blank=True)
    supplier_name = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    supplier_url = models.CharField(max_length=512, null=True, blank=True)
    shipping_method = models.CharField(max_length=512, null=True, blank=True)
    variants_map = models.TextField(null=True, blank=True)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'<CommerceHQSupplier: {self.id}>'

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

        super(CommerceHQSupplier, self).save(*args, **kwargs)


class CommerceHQBoard(BoardBase):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=512)
    products = models.ManyToManyField('CommerceHQProduct', blank=True)
    config = models.CharField(max_length=512, blank=True, default='')
    favorite = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return f'<CommerceHQBoard: {self.id}>'

    def saved_count(self):
        return self.products.filter(store__is_active=True, source_id=0).count()

    def connected_count(self):
        return self.products.exclude(store__is_active=True, source_id=0).count()


class CommerceHQOrderTrack(OrderTrackBase):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    store = models.ForeignKey(CommerceHQStore, null=True, on_delete=models.CASCADE)
    order_id = models.BigIntegerField()
    line_id = models.BigIntegerField()
    commercehq_status = models.CharField(max_length=128, blank=True, null=True, default='', verbose_name="CHQ Fulfillment Status")

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

    def __str__(self):
        return f'<CommerceHQOrderTrack: {self.id}>'

    def save(self, *args, **kwargs):
        try:
            data = json.loads(self.data)
        except:
            data = None

        if data:
            if data.get('bundle'):
                status = []
                source_tracking = []
                end_reasons = []

                for key, val in list(data.get('bundle').items()):
                    if val.get('source_status'):
                        status.append(val.get('source_status'))

                    if val.get('source_tracking'):
                        source_tracking.append(val.get('source_tracking'))

                    if val.get('end_reason'):
                        end_reasons.append(val.get('end_reason'))

                self.source_status = ','.join(status)
                self.source_tracking = ','.join(source_tracking)
                self.source_status_details = ','.join(end_reasons)

            else:
                self.source_status_details = json.loads(self.data)['aliexpress']['end_reason']

        if self.source_id:
            source_id = str(self.source_id).strip(' ,')
            if ',' in source_id:
                source_id = [i.strip() for i in list(filter(len, re.split('[, ]+', self.source_id)))]
                source_id = ','.join(source_id)

            if self.source_id != source_id:
                self.source_id = source_id

        super(CommerceHQOrderTrack, self).save(*args, **kwargs)

    def encoded(self):
        return base64_encode(json.dumps(self.data))

    def get_commercehq_link(self):
        return self.store.get_admin_url('orders', self.order_id)

    def get_tracking_link(self):
        aftership_domain = 'http://track.aftership.com/{{tracking_number}}'

        if self.user.get_config('chq_custom_tracking'):
            aftership_domain = self.user.get_config('chq_custom_tracking', {}).get(str(self.store_id), aftership_domain)

            if '{{tracking_number}}' not in aftership_domain:
                aftership_domain = "http://{}.aftership.com/{{{{tracking_number}}}}".format(aftership_domain)
            elif not aftership_domain.startswith('http'):
                aftership_domain = 'http://{}'.format(re.sub('^([:/]*)', r'', aftership_domain))

        return aftership_domain.replace('{{tracking_number}}', self.source_tracking)

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

        if self.source_status and ',' in self.source_status:
            source_status = []
            for i in self.source_status.split(','):
                source_status.append(status_map.get(i))

            return ', '.join(set(source_status))

        else:
            return status_map.get(self.source_status)

    get_source_status.admin_order_field = 'source_status'

    def get_source_url(self):
        if self.source_id:
            if self.source_type == 'ebay':
                return 'https://vod.ebay.com/vod/FetchOrderDetails?purchaseOrderId={}'.format(self.source_id)
            else:
                return 'http://trade.aliexpress.com/order_detail.htm?orderId={}'.format(self.source_id)
        else:
            return None

    def get_source_ids(self):
        if self.source_id:
            return ', '.join(set(['#{}'.format(i) for i in self.source_id.split(',')]))


class CommerceHQUserUpload(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(CommerceHQProduct, null=True, on_delete=models.CASCADE)
    url = models.CharField(max_length=512, blank=True, default='', verbose_name="Upload file URL")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return f'<CommerceHQUserUpload: {self.id}>'
