from django.shortcuts import reverse
from django.utils.html import format_html

from bs4 import BeautifulSoup

import commercehq_core
import gearbubble_core
import leadgalaxy
import woocommerce_core
import bigcommerce_core


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

    @classmethod
    def get_store_type(cls, store):
        # Prevents cyclic dependency.
        ShopifyStore = leadgalaxy.models.ShopifyStore
        CommerceHQStore = commercehq_core.models.CommerceHQStore
        WooStore = woocommerce_core.models.WooStore
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
        amount = sum(self.payout_items.values_list('amount', flat=True))
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
