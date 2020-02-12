from django.shortcuts import reverse

from product_common import models as base_models


class Product(base_models.Product):
    PRODUCT_TYPE = 'dropified'

    def get_url(self):
        return reverse('dropified_product:product_detail',
                       kwargs={'product_id': self.id})


class ProductImage(base_models.ProductImage):
    pass


class Order(base_models.Order):
    pass


class OrderLine(base_models.OrderLine):
    pass


class Payout(base_models.Payout):
    pass
