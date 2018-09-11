from django.utils.html import strip_tags
from django.utils import timezone
from django.conf import settings

import os
import re
import time
import urllib
from math import ceil
from tempfile import NamedTemporaryFile
from urlparse import urlparse

from loxun import XmlWriter

from shopified_core.utils import safeStr
from leadgalaxy.utils import (
    aws_s3_upload,
    get_shopify_products_count,
    get_shopify_products
)

from commercehq_core.utils import (
    get_chq_products_count,
    get_chq_products
)

from woocommerce_core.utils import (
    get_woo_products_count,
    get_woo_products
)

from .models import FeedStatus, CommerceHQFeedStatus, WooFeedStatus, GearBubbleFeedStatus


def safeInt(v, default=0):
    try:
        return int(v)
    except:
        return default


class ProductFeed():
    def __init__(self, store, revision=1, all_variants=True, include_variants=True, default_product_category=''):
        self.store = store
        self.info = store.get_info

        self.currency = self.info['currency']
        self.domain = self.info['domain']

        self.revision = safeInt(revision, 1)
        self.all_variants = all_variants
        self.include_variants = include_variants
        self.default_product_category = default_product_category

    def _add_element(self, tag, text):
        self.writer.startTag(tag)
        self.writer.text(text)
        self.writer.endTag()

    def init(self):
        self.out = NamedTemporaryFile(suffix='.xml', prefix='feed_', delete=False)
        self.writer = XmlWriter(self.out, pretty=True, indent='')

        self.writer.addNamespace("g", "http://base.google.com/ns/1.0")

        self.writer.startTag("rss", {"version": "2.0"})
        self.writer.startTag("channel")

        self._add_element('title', self.info['name'])
        self._add_element('link', 'https://{}'.format(self.info['domain']))
        self._add_element('description', u'{} Products Feed'.format(self.info['name']))

    def save(self):
        self.writer.endTag()
        self.writer.endTag()
        self.writer.close()

        self.out.close()

        return self.out

    def generate_feed(self):
        limit = 200
        count = get_shopify_products_count(self.store)

        if not count:
            return

        if count > 5000:
            print 'Ignore Feed for ', self.store.shop, 'with', count, 'Products'
            return

        pages = int(ceil(count / float(limit)))
        for page in xrange(1, pages + 1):
            products = get_shopify_products(store=self.store, page=page, limit=limit, all_products=False)
            for p in products:
                self.add_product(p)

    def add_product(self, product):
        if len(product['variants']) and product.get('published_at'):
            self.images_map = {}

            for i in product['images']:
                self.images_map[i['id']] = i['src']

            # Add the first variant with Product ID
            self._add_variant(product, product['variants'][0], variant_id=product['id'])

            if self.include_variants:
                for variant in product['variants']:
                    self._add_variant(product, variant, var_image=True)

                    if not self.all_variants:
                        break

    def _add_variant(self, product, variant, variant_id=None, var_image=False):
        image = product.get('image')
        if image:
            image = image.get('src')
        else:
            return None

        self.writer.startTag('item')

        if variant_id is None:
            variant_id = variant['id']

        if var_image and variant.get('image_id') in self.images_map:
            image = self.images_map[variant['image_id']]

        if self.revision == 1:
            self._add_element('g:id', 'store_{p[id]}_{v[id]}'.format(p=product, v=variant))
        else:
            self._add_element('g:id', 'shopify_{}'.format(variant_id))
            self._add_element('g:item_group_id', '{}'.format(variant_id))

        self._add_element('g:link', u'https://{domain}/products/{p[handle]}?variant={v[id]}'.format(domain=self.domain, p=product, v=variant))
        self._add_element('g:title', product.get('title'))
        self._add_element('g:description', self._clean_description(product))
        self._add_element('g:image_link', image)
        self._add_element('g:price', '{amount} {currency}'.format(amount=variant.get('price'), currency=self.currency))
        self._add_element('g:shipping_weight', '{variant[weight]} {variant[weight_unit]}'.format(variant=variant))
        self._add_element('g:brand', product.get('vendor'))
        self._add_element('g:google_product_category', safeStr(product.get('product_type') or self.default_product_category))
        self._add_element('g:availability', 'in stock')
        self._add_element('g:condition', 'new')

        self.writer.endTag()

    def _clean_description(self, product):
        text = product.get('body_html') or ''
        text = re.sub('<br */?>', '\n', text)
        text = strip_tags(text).strip()

        if len(text) == 0:
            text = product.get('title', '')

        return text

    def out_file(self):
        return self.out

    def out_filename(self):
        return self.out.name

    def delete_out(self):
        os.unlink(self.out.name)


class CommerceHQProductFeed():
    def __init__(self, store, revision=1, all_variants=True, include_variants=True, default_product_category=''):
        self.store = store

        domain = urlparse(store.api_url).netloc
        self.info = {'currency': 'USD', 'domain': domain, 'name': store.title}

        self.currency = self.info['currency']
        self.domain = self.info['domain']

        self.revision = safeInt(revision, 1)
        self.all_variants = all_variants
        self.include_variants = include_variants
        self.default_product_category = default_product_category

    def _add_element(self, tag, text):
        self.writer.startTag(tag)
        self.writer.text(text)
        self.writer.endTag()

    def init(self):
        self.out = NamedTemporaryFile(suffix='.xml', prefix='chq_feed_', delete=False)
        self.writer = XmlWriter(self.out, pretty=True, indent='')

        self.writer.addNamespace("g", "http://base.google.com/ns/1.0")

        self.writer.startTag("rss", {"version": "2.0"})
        self.writer.startTag("channel")

        self._add_element('title', self.store.title)
        self._add_element('link', self.store.get_store_url())
        self._add_element('description', u'{} Products Feed'.format(self.store.title))

    def save(self):
        self.writer.endTag()
        self.writer.endTag()
        self.writer.close()

        self.out.close()

        return self.out

    def generate_feed(self):
        limit = 200
        count = get_chq_products_count(self.store)

        if not count:
            return

        if count > 5000:
            print 'Ignore Feed for CHQ', self.store.id, 'with', count, 'Products'
            return

        pages = int(ceil(count / float(limit)))
        for page in xrange(1, pages + 1):
            products = get_chq_products(store=self.store, page=page, limit=limit, all_products=False)
            for p in products:
                self.add_product(p)

    def add_product(self, product):
        if product.get('is_draft'):
            return

        if product.get('is_multi'):
            for variant in product.get('variants', []):
                self._add_variant(product, variant)

                if not self.all_variants:
                    break
        else:
            self._add_variant(product, None)

    def _add_variant(self, product, variant, variant_id=None):
        if variant is None:
            variant = {
                'id': 0,
                'price': product['price']
            }

        if variant.get('images'):
            image = variant.get('images')[0].get('path')
        elif product.get('images'):
            image = product.get('images')[0].get('path')
        else:
            image = self.store.get_store_url()

        self.writer.startTag('item')

        if variant_id is None:
            variant_id = variant['id']

        self._add_element('g:id', 'store_{p[id]}_{v[id]}'.format(p=product, v=variant))

        self._add_element('g:link', self.store.get_store_url('products', product['seo_url']))
        self._add_element('g:title', product.get('title'))
        self._add_element('g:description', product.get('title'))
        self._add_element('g:image_link', image)
        self._add_element('g:price', '{amount} {currency}'.format(amount=variant.get('price'), currency=self.currency))
        self._add_element('g:shipping_weight', '{product[shipping_weight]} kg'.format(product=product))
        self._add_element('g:brand', product.get('vendor') or '')
        self._add_element('g:google_product_category', safeStr(product.get('type') or self.default_product_category))
        self._add_element('g:availability', 'in stock')
        self._add_element('g:condition', 'new')

        self.writer.endTag()

    def out_file(self):
        return self.out

    def out_filename(self):
        return self.out.name

    def delete_out(self):
        os.unlink(self.out.name)


class WooProductFeed():
    def __init__(self, store, revision=1, all_variants=True, include_variants=True, default_product_category=''):
        self.store = store

        domain = urlparse(store.api_url).netloc
        self.info = {'currency': self._get_store_currency(), 'domain': domain, 'name': store.title}

        self.currency = self.info['currency']
        self.domain = self.info['domain']

        self.revision = safeInt(revision, 1)
        self.all_variants = all_variants
        self.include_variants = include_variants
        self.default_product_category = default_product_category
        self.weight_unit = self._get_store_weight_unit()

    def _add_element(self, tag, text):
        self.writer.startTag(tag)
        self.writer.text(text)
        self.writer.endTag()

    def init(self):
        self.out = NamedTemporaryFile(suffix='.xml', prefix='woo_feed_', delete=False)
        self.writer = XmlWriter(self.out, pretty=True, indent='')

        self.writer.addNamespace("g", "http://base.google.com/ns/1.0")

        self.writer.startTag("rss", {"version": "2.0"})
        self.writer.startTag("channel")

        self._add_element('title', self.store.title)
        self._add_element('link', self.store.get_store_url())
        self._add_element('description', u'{} Products Feed'.format(self.store.title))

    def save(self):
        self.writer.endTag()
        self.writer.endTag()
        self.writer.close()

        self.out.close()

        return self.out

    def generate_feed(self):
        limit = 100
        count = get_woo_products_count(self.store)

        if not count:
            return

        pages = int(ceil(count / float(limit)))
        for page in xrange(1, pages + 1):
            products = get_woo_products(store=self.store, page=page, limit=limit, all_products=False)
            for p in products:
                self.add_product(p)

    def add_product(self, product):
        if not product['status'] == 'publish':
            return

        if self.include_variants and len(product['variations']) > 0:
            variants = self._get_variants(product['id'])
            for variant in variants:
                self._add_variant(product, variant)
                if not self.all_variants:
                    break

        else:
            self._add_variant(product, None)

    def _get_variants(self, source_id):
        variants = []
        page = 1
        while page:
            params = urllib.urlencode({'page': page, 'per_page': 100})
            path = 'products/{}/variations?{}'.format(source_id, params)
            r = self.store.wcapi.get(path)
            r.raise_for_status()
            fetched_variants = r.json()
            variants.extend(fetched_variants)
            has_next = 'rel="next"' in r.headers.get('link', '')
            page = page + 1 if has_next else 0

        return variants

    def _get_store_weight_unit(self):
        r = self.store.wcapi.get('settings/products/woocommerce_weight_unit')
        r.raise_for_status()

        return r.json()['value']

    def _get_store_currency(self):
        r = self.store.wcapi.get('settings/general/woocommerce_currency')
        r.raise_for_status()

        return r.json()['value']

    def _add_variant(self, product, variant, variant_id=None):
        if variant:
            image = variant['image'].get('src')
        else:
            image = next(iter(product['images']), {}).get('src', '')

        element = product if variant is None else variant

        if variant is None:
            variant = {'id': 0}

        self.writer.startTag('item')

        self._add_element('g:id', 'store_{p[id]}_{v[id]}'.format(p=product, v=variant))
        self._add_element('g:link', element['permalink'])
        self._add_element('g:title', product.get('name', ''))
        self._add_element('g:description', element['description'])
        self._add_element('g:image_link', image)
        self._add_element('g:price', '{amount} {currency}'.format(amount=element['price'], currency=self.currency))
        self._add_element('g:shipping_weight', '{} {}'.format(element['weight'], self.weight_unit))
        self._add_element('g:google_product_category', self.default_product_category)
        self._add_element('g:availability', 'in stock')
        self._add_element('g:condition', 'new')

        self.writer.endTag()

    def out_file(self):
        return self.out

    def out_filename(self):
        return self.out.name

    def delete_out(self):
        os.unlink(self.out.name)


class GearBubbleProductFeed(object):
    def __init__(self, store, revision=1, all_variants=True, include_variants=True, default_product_category=''):
        domain = urlparse(store.get_api_url('')).netloc
        self.info = {'currency': self._get_store_currency(), 'domain': domain, 'name': store.title}
        self.store = store
        self.currency = self.info['currency']
        self.domain = self.info['domain']
        self.revision = safeInt(revision, 1)
        self.all_variants = all_variants
        self.include_variants = include_variants
        self.default_product_category = default_product_category

    def _add_element(self, tag, text):
        self.writer.startTag(tag)
        self.writer.text(text)
        self.writer.endTag()

    def init(self):
        self.out = NamedTemporaryFile(suffix='.xml', prefix='gear_feed_', delete=False)
        self.writer = XmlWriter(self.out, pretty=True, indent='')
        self.writer.addNamespace("g", "http://base.google.com/ns/1.0")
        self.writer.startTag("rss", {"version": "2.0"})
        self.writer.startTag("channel")
        self._add_element('title', self.store.title)
        self._add_element('link', self.store.get_store_url())
        self._add_element('description', u'{} Products Feed'.format(self.store.title))

    def save(self):
        self.writer.endTag()
        self.writer.endTag()
        self.writer.close()
        self.out.close()

        return self.out

    def generate_feed(self):
        for p in self.store.get_gearbubble_products():
            self.add_product(p)

    def add_product(self, product):
        has_variants = bool(product.get('variants'))

        if self.include_variants and has_variants:
            variants = product.get('variants')
            variants = variants if self.all_variants else variants[:1]

            for variant in variants:
                self._add_variant(product, variant)
        else:
            self._add_variant(product, None)

    def _get_store_currency(self):
        """
        Returns USD for now because there is no way to check for store currency
        """
        return 'USD'

    def _add_variant(self, product_data, variant):
        image = next(iter(product_data.get('images', [])), {}).get('src', '')
        variant_id = 0
        permalink = '{}/private_products/{}'.format(self.store.get_store_url(), product_data['slug'])
        body_html = product_data.get('body_html') or ''
        description = strip_tags(body_html)

        if variant:
            images = product_data.get('images', [])
            images_by_id = {image['id']: image for image in images}
            image = images_by_id.get(variant['image_id'], {}).get('src', '')
            variant_id = variant['id']

        self.writer.startTag('item')

        self._add_element('g:id', 'store_{}_{}'.format(product_data['id'], variant_id))
        self._add_element('g:link', permalink)
        self._add_element('g:title', product_data['title'])
        self._add_element('g:description', description)
        self._add_element('g:image_link', image)

        if variant:
            self._add_element('g:price', '{amount} {currency}'.format(amount=variant['price'], currency=self.currency))
            self._add_element('g:shipping_weight', '{} {}'.format(variant['weight'], variant['weight_unit']))

        self._add_element('g:google_product_category', self.default_product_category)
        self._add_element('g:availability', 'in stock')
        self._add_element('g:condition', 'new')

        self.writer.endTag()

    def out_file(self):
        return self.out

    def out_filename(self):
        return self.out.name

    def delete_out(self):
        os.unlink(self.out.name)


def get_store_feed(store):
    try:
        return FeedStatus.objects.get(store=store)

    except FeedStatus.DoesNotExist:
        return FeedStatus.objects.create(
            store=store,
            updated_at=None
        )


def get_chq_store_feed(store):
    try:
        return CommerceHQFeedStatus.objects.get(store=store)

    except CommerceHQFeedStatus.DoesNotExist:
        return CommerceHQFeedStatus.objects.create(
            store=store,
            updated_at=None
        )


def get_woo_store_feed(store):
    try:
        return WooFeedStatus.objects.get(store=store)
    except WooFeedStatus.DoesNotExist:
        return WooFeedStatus.objects.create(store=store, updated_at=None)


def get_gear_store_feed(store):
    try:
        return GearBubbleFeedStatus.objects.get(store=store)
    except GearBubbleFeedStatus.DoesNotExist:
        return GearBubbleFeedStatus.objects.create(store=store, updated_at=None)


def generate_product_feed(feed_status, nocache=False):
    store = feed_status.store

    if not store.user.can('product_feeds.use'):
        return False

    feed_start = time.time()

    if not feed_status.feed_exists() or nocache:
        feed = ProductFeed(store,
                           feed_status.revision,
                           feed_status.all_variants,
                           feed_status.include_variants_id,
                           feed_status.default_product_category)

        feed.init()

        feed_status.status = 2
        feed_status.save()

        feed.generate_feed()
        feed.save()

        feed_status.generation_time = time.time() - feed_start
        feed_status.updated_at = timezone.now()

        feed_s3_url, upload_time = aws_s3_upload(
            filename=feed_status.get_filename(),
            input_filename=feed.out_filename(),
            mimetype='application/xml',
            upload_time=True,
            compress=True,
            bucket_name=settings.S3_PRODUCT_FEED_BUCKET
        )

        feed.delete_out()

    else:
        feed_s3_url = feed_status.get_url()

    feed_status.status = 1
    feed_status.save()

    return feed_s3_url


def generate_chq_product_feed(feed_status, nocache=False):
    store = feed_status.store

    if not store.user.can('product_feeds.use'):
        return False

    feed_start = time.time()

    if not feed_status.feed_exists() or nocache:
        feed = CommerceHQProductFeed(store,
                                     feed_status.revision,
                                     feed_status.all_variants,
                                     feed_status.include_variants_id,
                                     feed_status.default_product_category)

        feed.init()

        feed_status.status = 2
        feed_status.save()

        feed.generate_feed()
        feed.save()

        feed_status.generation_time = time.time() - feed_start
        feed_status.updated_at = timezone.now()

        feed_s3_url, upload_time = aws_s3_upload(
            filename=feed_status.get_filename(),
            input_filename=feed.out_filename(),
            mimetype='application/xml',
            upload_time=True,
            compress=True,
            bucket_name=settings.S3_PRODUCT_FEED_BUCKET
        )

        feed.delete_out()

    else:
        feed_s3_url = feed_status.get_url()

    feed_status.status = 1
    feed_status.save()

    return feed_s3_url


def generate_woo_product_feed(feed_status, nocache=False):
    store = feed_status.store

    if not store.user.can('product_feeds.use'):
        return False

    feed_start = time.time()

    if not feed_status.feed_exists() or nocache:
        feed = WooProductFeed(store,
                              feed_status.revision,
                              feed_status.all_variants,
                              feed_status.include_variants_id,
                              feed_status.default_product_category)

        feed.init()

        feed_status.status = 2
        feed_status.save()

        feed.generate_feed()
        feed.save()

        feed_status.generation_time = time.time() - feed_start
        feed_status.updated_at = timezone.now()

        feed_s3_url, upload_time = aws_s3_upload(
            filename=feed_status.get_filename(),
            input_filename=feed.out_filename(),
            mimetype='application/xml',
            upload_time=True,
            compress=True,
            bucket_name=settings.S3_PRODUCT_FEED_BUCKET
        )

        feed.delete_out()

    else:
        feed_s3_url = feed_status.get_url()

    feed_status.status = 1
    feed_status.save()

    return feed_s3_url


def generate_gear_product_feed(feed_status, nocache=False):
    store = feed_status.store

    if not store.user.can('product_feeds.use'):
        return False

    feed_start = time.time()

    if not feed_status.feed_exists() or nocache:
        feed = GearBubbleProductFeed(store,
                                     feed_status.revision,
                                     feed_status.all_variants,
                                     feed_status.include_variants_id,
                                     feed_status.default_product_category)

        feed.init()

        feed_status.status = 2
        feed_status.save()

        feed.generate_feed()
        feed.save()

        feed_status.generation_time = time.time() - feed_start
        feed_status.updated_at = timezone.now()

        feed_s3_url, upload_time = aws_s3_upload(
            filename=feed_status.get_filename(),
            input_filename=feed.out_filename(),
            mimetype='application/xml',
            upload_time=True,
            compress=True,
            bucket_name=settings.S3_PRODUCT_FEED_BUCKET
        )

        feed.delete_out()

    else:
        feed_s3_url = feed_status.get_url()

    feed_status.status = 1
    feed_status.save()

    return feed_s3_url
