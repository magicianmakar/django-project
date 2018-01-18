from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string

import re
import textwrap
import simplejson as json
import urlparse

import requests
from pusher import Pusher

from shopified_core.utils import hash_url_filename


def add_to_class(cls, name):
    def _decorator(*args, **kwargs):
        cls.add_to_class(name, args[0])
    return _decorator


def safeStr(v, default=''):
    """ Always return a str object """

    if isinstance(v, basestring):
        return v
    else:
        return default


@add_to_class(User, 'get_chq_boards')
def user_get_chq_boards(self):
    if self.is_subuser:
        return self.profile.subuser_parent.get_chq_boards()
    else:
        return self.commercehqboard_set.all().order_by('title')


class CommerceHQStore(models.Model):
    class Meta:
        verbose_name = 'CHQ Store'
        ordering = ['-created_at']

    user = models.ForeignKey(User)
    title = models.CharField(max_length=300, blank=True, default='')
    api_url = models.CharField(max_length=512)
    api_key = models.CharField(max_length=300)
    api_password = models.CharField(max_length=300)

    is_active = models.BooleanField(default=True)
    store_hash = models.CharField(unique=True, default='', max_length=50, editable=False)

    list_index = models.IntegerField(default=0)
    auto_fulfill = models.CharField(max_length=50, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.store_hash:
            self.store_hash = get_random_string(32, 'abcdef0123456789')

        try:
            self.auto_fulfill = self.user.get_config('auto_shopify_fulfill', '')
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

        return u'https://{}'.format(url)

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


class CommerceHQProduct(models.Model):
    class Meta:
        verbose_name = 'CHQ Product'
        ordering = ['-created_at']

    store = models.ForeignKey('CommerceHQStore', related_name='products')
    user = models.ForeignKey(User)

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

    monitor_id = models.IntegerField(default=0, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        try:
            title = self.title
            if len(title) > 79:
                return u'{}...'.format(textwrap.wrap(title, width=79)[0])
            elif title:
                return title
            else:
                return u'<CommerceHQProduct: %d>' % self.id
        except:
            return u'<CommerceHQProduct: %d>' % self.id

    def save(self, *args, **kwargs):
        data = json.loads(self.data)

        self.title = data.get('title', '')
        self.tag = safeStr(data.get('tags', ''))[:1024]
        self.product_type = safeStr(data.get('type', ''))[:254]

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

    def have_supplier(self):
        try:
            return self.default_supplier is not None
        except:
            return False

    def get_chq_id(self):
        return self.source_id if self.store else None

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

    def set_suppliers_mapping(self, mapping):
        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.supplier_map = mapping
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

    #
    def set_bundle_mapping(self, mapping):
        bundle_map = self.get_bundle_mapping()
        bundle_map.update(mapping)

        self.bundle_map = json.dumps(bundle_map)

    def get_suppier_for_variant(self, variant_id):
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

    def set_shipping_mapping(self, mapping, update=True):
        if update:
            try:
                current = json.loads(self.shipping_map)
            except:
                current = {}

            for k, v in mapping.items():
                current[k] = v

            mapping = current

        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.shipping_map = mapping
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

    def set_variant_mapping(self, mapping, supplier=None, update=False):
        if supplier is None:
            supplier = self.default_supplier

        if update:
            try:
                current = json.loads(supplier.variants_map)
            except:
                current = {}

            for k, v in mapping.items():
                current[k] = v

            mapping = current

        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        if supplier:
            supplier.variants_map = mapping
            supplier.save()
        else:
            self.variants_map = mapping
            self.save()

    def get_variant_mapping(self, name=None, default=None, for_extension=False, supplier=None, mapping_supplier=False):
        mapping = {}

        if supplier is None:
            if mapping_supplier:
                supplier = self.get_suppier_for_variant(name)
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

        if for_extension and type(mapping) in [str, unicode]:
            mapping = mapping.split(',')

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

                    options = map(lambda a: {'title': a}, options)

                try:
                    if type(options) not in [list, dict]:
                        options = json.loads(options)

                        if type(options) is int:
                            options = str(options)
                except:
                    pass

                variants_map[str(v['id'])] = options
                seen_variants.append(str(v['id']))

            for k in variants_map.keys():
                if k not in seen_variants:
                    del variants_map[k]

            all_mapping[str(supplier.id)] = variants_map

        return all_mapping

    def get_common_images(self):
        common_images = set()
        image_urls = self.parsed.get('images', [])

        if not self.source_id:
            hashed_variant_images = self.parsed.get('variants_images', {}).keys()

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
        if self.have_supplier:
            url = self.default_supplier.product_url

            try:
                domain = urlparse.urlparse(url).hostname
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


class CommerceHQSupplier(models.Model):
    store = models.ForeignKey(CommerceHQStore, related_name='suppliers')
    product = models.ForeignKey(CommerceHQProduct)

    product_url = models.CharField(max_length=512, null=True, blank=True)
    supplier_name = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    supplier_url = models.CharField(max_length=512, null=True, blank=True)
    shipping_method = models.CharField(max_length=512, null=True, blank=True)
    variants_map = models.TextField(null=True, blank=True)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        if self.supplier_name:
            return self.supplier_name
        elif self.supplier_url:
            return self.supplier_url
        else:
            return u'<CommerceHQSupplier: {}>'.format(self.id)

    def get_source_id(self):
        try:
            if 'aliexpress.com' in self.product_url.lower():
                return int(re.findall('[/_]([0-9]+).html', self.product_url)[0])
        except:
            return None

    def get_store_id(self):
        try:
            if 'aliexpress.com' in self.supplier_url.lower():
                return int(re.findall('/([0-9]+)', self.supplier_url).pop())
        except:
            return None

    def short_product_url(self):
        source_id = self.get_source_id()
        if source_id:
            if 'aliexpress.com' in self.product_url.lower():
                return u'https://www.aliexpress.com/item//{}.html'.format(source_id)

        return self.product_url

    def support_auto_fulfill(self):
        """
        Return True if this supplier support auto fulfill using the extension
        Currently only Aliexpress support that
        """

        return 'aliexpress.com/' in self.product_url.lower()

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

            name = u'Supplier #{}'.format(supplier_idx)

        return name


class CommerceHQBoard(models.Model):
    class Meta:
        verbose_name = "CHQ Board"
        verbose_name_plural = "CHQ Boards"

    user = models.ForeignKey(User)
    title = models.CharField(max_length=512)
    products = models.ManyToManyField('CommerceHQProduct', blank=True)
    config = models.CharField(max_length=512, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return self.title

    def saved_count(self):
        return self.products.filter(store__is_active=True, source_id=0).count()

    def connected_count(self):
        return self.products.exclude(store__is_active=True, source_id=0).count()


class CommerceHQOrderTrack(models.Model):
    class Meta:
        ordering = ['-created_at']
        index_together = ['store', 'order_id', 'line_id']

    user = models.ForeignKey(User)
    store = models.ForeignKey(CommerceHQStore, null=True)
    order_id = models.BigIntegerField()
    line_id = models.BigIntegerField()
    commercehq_status = models.CharField(max_length=128, blank=True, null=True, default='', verbose_name="CHQ Fulfillment Status")

    source_id = models.CharField(max_length=512, blank=True, default='', db_index=True, verbose_name="Source Order ID")
    source_status = models.CharField(max_length=128, blank=True, default='', verbose_name="Source Order Status")
    source_tracking = models.CharField(max_length=128, blank=True, default='', verbose_name="Source Tracking Number")
    source_status_details = models.CharField(max_length=512, blank=True, null=True, verbose_name="Source Status Details")

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
            data = json.loads(self.data)
        except:
            data = None

        if data:
            if data.get('bundle'):
                status = []
                source_tracking = []
                end_reasons = []

                for key, val in data.get('bundle').items():
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
        return json.dumps(self.data).encode('base64')

    def get_commercehq_link(self):
        return self.store.get_admin_url('orders', self.order_id)

    def get_tracking_link(self):
        aftership_domain = 'http://track.aftership.com/{{tracking_number}}'

        if type(self.user.get_config('aftership_domain')) is dict:
            aftership_domain = self.user.get_config('aftership_domain').get(str(self.store_id), aftership_domain)

            if '{{tracking_number}}' not in aftership_domain:
                aftership_domain = "http://{}.aftership.com/{{{{tracking_number}}}}".format(aftership_domain)
            elif not aftership_domain.startswith('http'):
                aftership_domain = 'http://{}'.format(re.sub('^([:/]*)', r'', aftership_domain))

        return aftership_domain.replace('{{tracking_number}}', self.source_tracking)

    def get_source_status(self):
        status_map = {
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

            # Dropwow Status
            'P': "In Process",
            'C': "Complete",
            'O': "Open",
            'F': "Failed",
            'D': "Declined",
            'B': "Backordered",
            'I': "Cancelled",
            'Y': "Awaiting Call",
        }

        if self.source_status and ',' in self.source_status:
            source_status = []
            for i in self.source_status.split(','):
                source_status.append(status_map.get(i))

            return ', '.join(set(source_status))

        else:
            return status_map.get(self.source_status)

    get_source_status.admin_order_field = 'source_status'

    def get_source_status_color(self):
        if not self.source_status:
            return 'danger'
        elif self.source_status == 'FINISH':
            return 'primary'
        else:
            return 'warning'

    def get_source_url(self):
        if self.source_id:
            return 'http://trade.aliexpress.com/order_detail.htm?orderId={}'.format(self.source_id)
        else:
            return None

    def get_source_ids(self):
        if self.source_id:
            return u', '.join(set([u'#{}'.format(i) for i in self.source_id.split(',')]))

    def __unicode__(self):
        return u'{} | {}'.format(self.order_id, self.line_id)


class CommerceHQUserUpload(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(User)
    product = models.ForeignKey(CommerceHQProduct, null=True)
    url = models.CharField(max_length=512, blank=True, default='', verbose_name="Upload file URL")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return self.url.replace('%2F', '/').split('/')[-1]
