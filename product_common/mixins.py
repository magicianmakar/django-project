from django.db.models import Q
from django.shortcuts import reverse
from django.utils.html import format_html

import bigcommerce_core
import commercehq_core
import ebay_core
import facebook_core
import google_core
import gearbubble_core
import leadgalaxy
import woocommerce_core


class ProductMixin:
    is_admin_editable = True

    @property
    def to_real_product(self):
        from dropified_product.models import Product as DropifiedProduct
        if self.product_type == DropifiedProduct.PRODUCT_TYPE:
            return DropifiedProduct.objects.get(id=self.id)

        raise Exception("Invalid product")

    @property
    def thumbnail(self):
        return self.images.filter(position=0).get().image_url

    @property
    def description_short(self):
        from bs4 import BeautifulSoup

        description = BeautifulSoup(self.description, features="lxml")
        words = description.text.split()
        if len(words) > 8:
            return ' '.join(words[:8]) + '...'

        return description.text

    def to_dict(self):
        image_urls = [i.image_url for i in self.images.all()]

        data = dict(
            title=self.title,
            cost_price=self.cost_price,
            description=self.description,
            tags=self.tags,
            category=self.category,
            image_urls=image_urls,
            shipstation_sku=self.shipstation_sku,
            product_id=self.id,
            product_type=self.product_type,
        )
        return data

    def get_url(self):
        return reverse('product_common:product_detail',
                       kwargs={'product_id': self.id})

    @property
    def is_approved(self):
        return False

    @property
    def is_awaiting_review(self):
        return False


class SupplierMixin:

    @classmethod
    def get_suppliers(self, shipping=True):
        excluded_suppliers = ['dropified', 'tlg']
        exclude_filter = Q(slug__in=excluded_suppliers)
        if shipping:
            return self.objects.exclude(exclude_filter)

        return self.objects.exclude(exclude_filter
                                    | Q(is_shipping_supplier=True))

    @classmethod
    def get_dropified_commission(self):
        return self.objects.get(slug='dropified').profit_percentage

    @classmethod
    def get_tlg_commission(self):
        return self.objects.get(slug='tlg').profit_percentage


class OrderMixin:

    @property
    def status_string(self):
        def get_string(color, value):
            label = f"<span class='label label-{color}'>{value}</span>"
            return format_html(label)

        for key, value in self.STATUSES:
            if self.status == key:
                if key == self.PAID:
                    return get_string('primary', value)
                elif key == self.PENDING:
                    return get_string('warning', value)
                else:
                    return get_string('default', value)

    @property
    def amount_string(self):
        return "${:.2f}".format(self.amount / 100.)

    @property
    def edit_url(self):
        return reverse('admin:product_common_order_change', args=(self.id,))

    def get_dropified_source_id(self):
        return str(self.id)

    @classmethod
    def get_store_type(cls, store):
        # Prevents cyclic dependency.
        ShopifyStore = leadgalaxy.models.ShopifyStore
        CommerceHQStore = commercehq_core.models.CommerceHQStore
        WooStore = woocommerce_core.models.WooStore
        EbayStore = ebay_core.models.EbayStore
        FBStore = facebook_core.models.FBStore
        GoogleStore = google_core.models.GoogleStore
        GearBubbleStore = gearbubble_core.models.GearBubbleStore
        BigCommerceStore = bigcommerce_core.models.BigCommerceStore

        if isinstance(store, ShopifyStore):
            return cls.SHOPIFY
        elif isinstance(store, CommerceHQStore):
            return cls.CHQ
        elif isinstance(store, WooStore):
            return cls.WOO
        elif isinstance(store, GearBubbleStore):
            return cls.GEAR
        elif isinstance(store, BigCommerceStore):
            return cls.BIGCOMMERCE
        elif isinstance(store, EbayStore):
            return cls.EBAY
        elif isinstance(store, FBStore):
            return cls.FB
        elif isinstance(store, GoogleStore):
            return cls.GOOGLE

        raise Exception("Invalid Store")

    @classmethod
    def get_shipstation_key(cls, store_type, store_id, order_id):
        return f'{store_type}-{store_id}-{order_id}'


class OrderLineMixin:

    @classmethod
    def exists(cls, store_type, store_id, order_id, line_id):
        return cls.objects.filter(store_type=store_type,
                                  store_id=store_id,
                                  store_order_id=order_id,
                                  line_id=line_id).exists()

    @classmethod
    def get_shipstation_key(cls, store_type, store_id, order_id, line_id):
        return f'{store_type}-{store_id}-{order_id}-{line_id}'


class PayoutMixin:

    @property
    def amount_string(self):
        amount = sum(self.payout_lines.values_list('pls_order__amount', flat=True))
        return "${:.2f}".format(amount / 100.)

    @property
    def status_string(self):
        def get_string(color, value):
            label = f"<span class='label label-{color}'>{value}</span>"
            return format_html(label)

        for key, value in self.STATUSES:
            if self.status == key:
                if key == self.PAID:
                    return get_string('primary', value)
                elif key == self.PENDING:
                    return get_string('warning', value)
                else:
                    return get_string('default', value)
