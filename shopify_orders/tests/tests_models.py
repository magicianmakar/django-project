from django.test import TestCase
from django.utils import timezone
from django.db.models import Max

from shopify_orders.models import *

import factory


class ShopifyOrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ShopifyOrder
        django_get_or_create = ['order_id']

    order_id = '5415135175'
    country_code = 'US'
    user_id = 1
    store_id = 1
    order_number = 31
    total_price = 100
    customer_id = 1
    created_at = timezone.now()
    updated_at = timezone.now()


class ShopifyOrderLineFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ShopifyOrderLine
        django_get_or_create = ['line_id']

    line_id = '1654811'
    shopify_product = 10000
    price = 10
    quantity = 100
    variant_id = 12345
    order = factory.SubFactory(ShopifyOrderFactory)


class UtilsTestCase(TestCase):
    def setUp(self):
        pass

    def create_lines(self, order_id, line_ids):
        lines = []

        order = ShopifyOrderFactory(order_id=order_id)
        for i in line_ids:
            lines.append(ShopifyOrderLineFactory(order=order, line_id=i[0], product_id=i[1]))

        return lines

    def test_connected_filter(self):
        # One Order with a connected line
        self.create_lines(1456789123, [(1789456, 0), (1789457, 0), (1789458, 0)])
        self.create_lines(2456789123, [(2789456, 0), (2789457, 1321654), (2789458, 0)])
        orders = ShopifyOrder.objects.annotate(connected=Max('shopifyorderline__product_id')).filter(connected__gt=0)

        values = orders.values_list('order_id', 'connected')
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0][0], 2456789123)
        self.assertEqual(values[0][1], 1321654)
        self.assertEqual(orders.count(), 1)

        ShopifyOrder.objects.all().delete()

        # One Order with multi connected lines
        self.create_lines(1456789123, [(1789456, 0), (1789457, 0), (1789458, 0)])
        self.create_lines(2456789123, [(2789456, 0), (2789457, 1321654), (2789458, 1321655)])
        orders = ShopifyOrder.objects.annotate(connected=Max('shopifyorderline__product_id')).filter(connected__gt=0)

        values = orders.values_list('order_id', 'connected')
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0][0], 2456789123)
        self.assertEqual(values[0][1], 1321655)
        self.assertEqual(orders.count(), 1)

        ShopifyOrder.objects.all().delete()

        # Two Orders with connected lines
        self.create_lines(1456789123, [(1789456, 0), (1789457, 156444), (1789458, 0)])
        self.create_lines(2456789123, [(2789456, 0), (2789457, 1321654), (2789458, 1321655)])
        orders = ShopifyOrder.objects.annotate(connected=Max('shopifyorderline__product_id')).filter(connected__gt=0)

        values = orders.values_list('order_id', 'connected')
        self.assertEqual(len(values), 2)
        self.assertTrue(2456789123 in [i[0] for i in values])
        self.assertEqual(orders.count(),  2)

        ShopifyOrder.objects.all().delete()

        # Two Orders without any connected lines
        self.create_lines(1456789123, [(1789456, 0), (1789457, 0), (1789458, 0)])
        self.create_lines(2456789123, [(2789456, 0), (2789457, 0), (2789458, 0)])
        orders = ShopifyOrder.objects.annotate(connected=Max('shopifyorderline__product_id')).filter(connected__gt=0)

        values = orders.values_list('order_id', 'connected')
        self.assertEqual(len(values), 0)
        self.assertEqual(orders.count(),  0)
