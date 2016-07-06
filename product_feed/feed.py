from django.utils.html import strip_tags
from django.conf import settings

import xml.etree.ElementTree as ET
import re
import hashlib

from .models import FeedStatus


def safeInt(v, default=0):
    try:
        return int(v)
    except:
        return default


class ProductFeed():
    def __init__(self, store, revision=1, all_variants=True):
        self.store = store
        self.info = store.get_info

        self.currency = self.info['currency']
        self.domain = self.info['domain']

        self.revision = safeInt(revision, 1)
        self.all_variants = all_variants

    def _add_element(self, parent, tag, text):
        element = ET.SubElement(parent, tag)
        element.text = text

        return element

    def init(self):
        self.root = ET.Element("rss")
        self.root.attrib['xmlns:g'] = 'http://base.google.com/ns/1.0'
        self.root.attrib['version'] = '2.0'

        self.channel = ET.SubElement(self.root, 'channel')

        self._add_element(self.channel, 'title', self.info['name'])
        self._add_element(self.channel, 'link', 'https://{}'.format(self.info['domain']))
        self._add_element(self.channel, 'description', '{} Products Feed'.format(self.info['name']))

    def add_product(self, product):
        if len(product['variants']):
            for variant in product['variants']:
                self._add_variant(product, variant)

                if not self.all_variants:
                    break

    def _add_variant(self, product, variant):
        image = product.get('image')
        if image:
            image = image.get('src')
        else:
            return None

        item = ET.SubElement(self.channel, 'item')

        if self.revision == 1:
            self._add_element(item, 'g:id', 'store_{p[id]}_{v[id]}'.format(p=product, v=variant))
        else:
            self._add_element(item, 'g:id', '{}'.format(variant['id']))

        self._add_element(item, 'g:link', 'https://{domain}/products/{p[handle]}?variant={v[id]}'.format(domain=self.domain, p=product, v=variant))
        self._add_element(item, 'g:title', product.get('title'))
        self._add_element(item, 'g:description', self._clean_description(product))
        self._add_element(item, 'g:image_link', image)
        self._add_element(item, 'g:price', '{amount} {currency}'.format(amount=variant.get('price'), currency=self.currency))
        self._add_element(item, 'g:shipping_weight', '{variant[weight]} {variant[weight_unit]}'.format(variant=variant))
        self._add_element(item, 'g:brand', product.get('vendor'))
        self._add_element(item, 'g:google_product_category', product.get('product_type'))
        self._add_element(item, 'g:availability', 'in stock')
        self._add_element(item, 'g:condition', 'new')

        return item

    def _clean_description(self, product):
        text = product.get('body_html', '')
        text = re.sub('<br */?>', '\n', text)
        text = strip_tags(text).strip()

        if len(text) == 0:
            text = product.get('title', '')

        return text

    def get_feed_stream(self):
        yield u'<?xml version="1.0" encoding="utf-8"?>'

        for i in ET.tostringlist(self.root, encoding='utf-8', method="xml"):
            yield i

    def get_feed(self, formated=False):
        xml = ET.tostring(self.root, encoding='utf-8', method="xml")

        if formated:
            return self.prettify(xml)
        else:
            return u'{}\n{}'.format(u'<?xml version="1.0" encoding="utf-8"?>', xml.decode('utf-8'))

    def prettify(self, xml_str):
        """Return a pretty-printed XML string for the Element.
        """
        from xml.dom import minidom

        reparsed = minidom.parseString(xml_str)
        return reparsed.toprettyxml(indent="  ")

    def save(self, filename=None):
        if filename is None:
            import tempfile
            filename = tempfile.NamedTemporaryFile(mode="wb", suffix=".xml", delete=False)

        tree = ET.ElementTree(self.root)
        tree.write(filename, encoding='utf-8', xml_declaration=True)

        return filename


def get_store_feed(store):
    try:
        return FeedStatus.objects.get(store=store)

    except FeedStatus.DoesNotExist:
        return FeedStatus.objects.create(
            store=store,
            updated_at=None
        )


def generate_product_feed(feed_status, nocache=False):
    import time
    from django.utils import timezone
    from leadgalaxy.utils import get_shopify_products, aws_s3_upload

    store = feed_status.store

    if not store.user.can('product_feeds.use'):
        return False

    feed_start = time.time()

    if not feed_status.feed_exists() or nocache:
        feed = ProductFeed(store, feed_status.revision, feed_status.all_variants)
        feed.init()

        feed_status.status = 2
        feed_status.save()

        for p in get_shopify_products(store, all_products=True):
            feed.add_product(p)

        feed_status.generation_time = time.time() - feed_start
        feed_status.updated_at = timezone.now()

        feed_s3_url, upload_time = aws_s3_upload(
            filename=feed_status.get_filename(),
            content=feed.get_feed(),
            mimetype='application/xml',
            upload_time=True,
            compress=True,
            bucket_name=settings.S3_PRODUCT_FEED_BUCKET
        )
    else:
        feed_s3_url = feed_status.get_url()

    feed_status.status = 1
    feed_status.save()

    return feed_s3_url
