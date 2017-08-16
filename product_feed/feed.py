from django.utils.html import strip_tags
from django.utils import timezone
from django.conf import settings

import os
import re
import time
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

from .models import FeedStatus, CommerceHQFeedStatus


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
            self._add_element('g:id', '{}'.format(variant_id))

        self._add_element('g:link', 'https://{domain}/products/{p[handle]}?variant={v[id]}'.format(domain=self.domain, p=product, v=variant))
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
