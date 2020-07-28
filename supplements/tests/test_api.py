import json
from unittest.mock import MagicMock, patch

from leadgalaxy.tests.factories import AppPermissionFactory, GroupPlanFactory, ShopifyProductFactory, ShopifyStoreFactory, UserFactory
from lib.test import BaseTestCase
from stripe_subscription.tests.factories import StripeCustomerFactory
from supplements.api import SupplementsApi
from supplements.models import AuthorizeNetCustomer
from supplements.models import PLSOrder as Order
from supplements.models import PLSOrderLine as OrderLine
from supplements.models import ShippingGroup

from .factories import (
    PLSupplementFactory,
    UserSupplementFactory,
    UserSupplementLabelFactory,
    PLSOrderLineFactory,
    PLSOrderFactory,
    ShippingGroupFactory,
)


class PLSBaseTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.supplement = PLSupplementFactory.create(
            title='Fish Oil',
            description='Fish oil is great',
            category='supplement',
            tags='supplement',
            cost_price='15.99',
            label_template_url='http://example.com',
            wholesale_price='10.00',
            weight='1',
        )

        self.user_supplement = UserSupplementFactory.create(
            title=self.supplement.title,
            description=self.supplement.description,
            category=self.supplement.category,
            tags=self.supplement.tags,
            user=self.user,
            pl_supplement=self.supplement,
            price="15.99",
            compare_at_price="20.00",
        )

        self.label = UserSupplementLabelFactory.create(
            user_supplement=self.user_supplement,
            url="http://example.com",
        )

        self.label.status = self.label.APPROVED
        self.label.save()

        self.user_supplement.current_label = self.label
        self.user_supplement.save()


class MakePaymentTestCase(PLSBaseTestCase):
    def setUp(self):
        super().setUp()

        stripe_customer = StripeCustomerFactory(user=self.user)
        stripe_customer.save()

        order_key = 'key'
        order_id = '1234'
        line_id = 12345678

        line_key = 'line-key'

        self.shipments = [{
            'orderKey': order_key,
            'trackingNumber': 'tracking-number',
            'items': [{'lineItemKey': line_key}],
        }]

        pl_supplement = self.user_supplement.pl_supplement
        US = ShippingGroup.objects.filter(slug='US')
        if US.exists():
            US = US.first()
            GB = ShippingGroup.objects.get(slug='GB')
        else:
            US = ShippingGroupFactory()
            GB = ShippingGroupFactory()
        pl_supplement.shipping_countries.add(US, GB)
        pl_supplement.save()

        self.store = ShopifyStoreFactory(primary_location=12)
        self.store.user = self.user
        self.store.save()
        store_id = self.store.id

        product = ShopifyProductFactory(
            user=self.user,
            shopify_id='13213123',
            user_supplement=self.user_supplement,
            store=self.store,
        )

        self.url = '/api/supplements/make-payment'
        self.order_data_ids = [
            f'{store_id}_{order_id}_{line_id}',
        ]

        self.data = {
            'order_data_ids': self.order_data_ids,
            'store_type': self.store.store_type,
            'store_id': self.store.id,
        }

        self.order_data = {
            'id': order_id,
            'name': 'Fake project',
            'currency': 'usd',
            'order_number': '1234',
            'created_at': '1/2/20',
            'shipping_address': {
                'name': self.user.get_full_name(),
                'company': 'Dropified',
                'address1': 'House 1',
                'address2': 'Street 1',
                'city': 'City',
                'province': 'State',
                'zip': '123456',
                'country_code': 'US',
                'country': 'United States',
                'phone': '1234567',
            },
            'line_items': [{
                'id': line_id,
                'name': 'Item name',
                'title': 'Item name',
                'quantity': 1,
                'product_id': product.shopify_id,
                'price': 1200,
                'sku': '123'
            }],
        }

        self.order_data_cache = {
            **self.order_data,
            'order_data_id': self.order_data_ids[0],
            'source_id': self.user_supplement.id,
            'order': {
                'phone': {
                    'number': '000000',
                    'country': '1'
                },
            },
        }

        self.transaction_id = '8888'

        self.mock_order_response = MagicMock()
        self.mock_order_response.json.return_value = {'order': self.order_data}
        self.mock_response = MagicMock()
        self.mock_response.json.return_value = {'orderKey': 'Test Key'}

        AuthorizeNetCustomer.objects.create(user=self.user)

        SupplementsApi.order_cache = {}
        SupplementsApi.product_cache = {}

    def test_post(self):
        self.do_test()

    def test_post_error(self):
        self.user_supplement.pl_supplement.shipping_countries.clear()
        GB = ShippingGroup.objects.get(slug='GB')
        self.user_supplement.pl_supplement.shipping_countries.add(GB)
        self.user_supplement.pl_supplement.save()
        self.do_test(count=0)

    def test_post_no_country(self):
        self.user_supplement.pl_supplement.save()

        self.do_test()

    def test_post_invalid_country(self):
        self.order_data['shipping_address']['country'] = 'US'

        self.do_test()

    def do_test(self, count=1):
        self.client.force_login(self.user)
        with patch('leadgalaxy.models.requests.get',
                   return_value=self.mock_order_response), \
                patch('shopified_core.api_base.order_data_cache',
                      return_value=self.order_data_cache), \
                patch('supplements.mixin.AuthorizeNetCustomerMixin.charge',
                      return_value=self.transaction_id), \
                patch('supplements.lib.shipstation.requests.post',
                      return_value=self.mock_response), \
                patch('leadgalaxy.tasks.update_shopify_order.apply_async',
                      return_value=True), \
                patch('leadgalaxy.tasks.order_save_changes.apply_async',
                      return_value=True), \
                patch('shopify_orders.tasks.check_track_errors.delay',
                      return_value=True), \
                patch('leadgalaxy.utils.get_shopify_order_line'), \
                patch('pusher.Pusher.trigger'):

            self.assertEqual(Order.objects.all().count(), 0)
            self.assertEqual(OrderLine.objects.all().count(), 0)

            response = self.client.post(self.url,
                                        data=json.dumps(self.data),
                                        content_type='application/json')

            self.assertEqual(response.status_code, 200)
            self.assertEqual(Order.objects.all().count(), count)
            self.assertEqual(OrderLine.objects.all().count(), count)


class MakePaymentBundleTestCase(PLSBaseTestCase):
    def setUp(self):
        super().setUp()

        stripe_customer = StripeCustomerFactory(user=self.user)
        stripe_customer.save()

        order_key = 'key'
        order_id = '1234'
        line_id = 12345678

        line_key = 'line-key'

        self.shipments = [{
            'orderKey': order_key,
            'trackingNumber': 'tracking-number',
            'items': [{'lineItemKey': line_key}],
        }]

        pl_supplement = self.user_supplement.pl_supplement
        US = ShippingGroup.objects.filter(slug='US')
        if US.exists():
            US = US.first()
            GB = ShippingGroup.objects.get(slug='GB')
        else:
            US = ShippingGroupFactory()
            GB = ShippingGroupFactory()
        pl_supplement.shipping_countries.add(US, GB)
        pl_supplement.save()

        self.store = ShopifyStoreFactory(primary_location=12)
        self.store.user = self.user
        self.store.save()
        store_id = self.store.id

        product = ShopifyProductFactory(
            user=self.user,
            shopify_id='13213123',
            user_supplement=self.user_supplement,
            store=self.store,
        )

        self.url = '/api/supplements/make-payment'
        self.order_data_ids = [
            f'{store_id}_{order_id}_{line_id}',
        ]

        self.data = {
            'order_data_ids': self.order_data_ids,
            'store_type': self.store.store_type,
            'store_id': self.store.id,
        }

        self.order_data = {
            'id': order_id,
            'name': 'Fake project',
            'currency': 'usd',
            'order_number': '1234',
            'created_at': '1/2/20',
            'shipping_address': {
                'name': self.user.get_full_name(),
                'company': 'Dropified',
                'address1': 'House 1',
                'address2': 'Street 1',
                'city': 'City',
                'province': 'State',
                'zip': '123456',
                'country_code': 'US',
                'country': 'United States',
                'phone': '1234567',
            },
            'line_items': [{
                'id': line_id,
                'name': 'Item name',
                'title': 'Item name',
                'quantity': 1,
                'product_id': product.shopify_id,
                'price': 1200,
                'sku': '123'
            }],
        }

        bundle_supplement = UserSupplementFactory.create(
            title='Bundle Supplement',
            user=self.user,
            pl_supplement=self.supplement,
            price="15.99",
            compare_at_price="20.00",
        )
        bundle_label = UserSupplementLabelFactory.create(
            user_supplement=bundle_supplement,
            url="http://example.com",
        )
        bundle_label.status = bundle_label.APPROVED
        bundle_label.save()
        bundle_supplement.current_label = bundle_label
        bundle_supplement.save()

        bundle_data = [{
            'title': self.supplement.title,
            'quantity': 2,
            'source_id': self.user_supplement.id,
            'supplier_type': 'pls',
        }, {
            'title': bundle_supplement.title,
            'quantity': 3,
            'source_id': bundle_supplement.id,
            'supplier_type': 'pls',
        }]

        self.order_data_cache = {
            **self.order_data,
            'order_data_id': self.order_data_ids[0],
            'source_id': self.user_supplement.id,
            'products': bundle_data,
            'is_bundle': len(bundle_data) > 0,
            'order': {
                'phone': {
                    'number': '000000',
                    'country': '1'
                },
            },
        }

        self.transaction_id = '8888'

        self.mock_order_response = MagicMock()
        self.mock_order_response.json.return_value = {'order': self.order_data}
        self.mock_response = MagicMock()
        self.mock_response.json.return_value = {'orderKey': 'Test Key'}

        AuthorizeNetCustomer.objects.create(user=self.user)

        SupplementsApi.order_cache = {}
        SupplementsApi.product_cache = {}

    def test_post(self):
        self.do_test()

    def test_post_error(self):
        self.user_supplement.pl_supplement.shipping_countries.clear()
        GB = ShippingGroup.objects.get(slug='GB')
        self.user_supplement.pl_supplement.shipping_countries.add(GB)
        self.user_supplement.pl_supplement.save()
        self.do_test(count=0, item_count=0)

    def test_post_no_country(self):
        self.user_supplement.pl_supplement.save()

        self.do_test()

    def test_post_invalid_country(self):
        self.order_data['shipping_address']['country'] = 'US'

        self.do_test()

    def do_test(self, count=1, item_count=2):
        self.client.force_login(self.user)
        with patch('leadgalaxy.models.requests.get',
                   return_value=self.mock_order_response), \
                patch('shopified_core.api_base.order_data_cache',
                      return_value=self.order_data_cache), \
                patch('supplements.mixin.AuthorizeNetCustomerMixin.charge',
                      return_value=self.transaction_id), \
                patch('supplements.lib.shipstation.requests.post',
                      return_value=self.mock_response), \
                patch('leadgalaxy.tasks.update_shopify_order.apply_async',
                      return_value=True), \
                patch('leadgalaxy.tasks.order_save_changes.apply_async',
                      return_value=True), \
                patch('shopify_orders.tasks.check_track_errors.delay',
                      return_value=True), \
                patch('leadgalaxy.utils.get_shopify_order_line'), \
                patch('pusher.Pusher.trigger'):

            self.assertEqual(Order.objects.all().count(), 0)
            self.assertEqual(OrderLine.objects.all().count(), 0)

            response = self.client.post(self.url,
                                        data=json.dumps(self.data),
                                        content_type='application/json')

            self.assertEqual(response.status_code, 200)
            self.assertEqual(Order.objects.all().count(), count)
            self.assertEqual(OrderLine.objects.all().count(), item_count)


class OrderLineInfoTestCase(PLSBaseTestCase):
    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def test_get_request_to_endpoint_returns_401_if_not_logged_in(self):
        r = self.client.get('/api/supplements/order-line-info?item_id=0')
        self.assertEqual(r.status_code, 401)

    def test_get_request_to_endpoint_returns_404_if_item_is_not_found(self):
        self.login()
        r = self.client.get('/api/supplements/order-line-info?item_id=0')
        self.assertEqual(r.status_code, 404)

    def test_get_request_to_endpoint_returns_200(self):
        self.login()
        order = PLSOrderFactory()
        line = PLSOrderLineFactory(store_id=order.store_id,
                                   store_order_id=order.store_order_id,
                                   pls_order=order,
                                   label=self.label)
        r = self.client.get(f'/api/supplements/order-line-info?item_id={line.id}')
        self.assertEqual(r.status_code, 200)

    def test_get_request_to_endpoint_returns_403_if_not_owner_of_label(self):
        self.login()
        order = PLSOrderFactory()
        user_supplement = UserSupplementFactory(user=UserFactory(), pl_supplement=PLSupplementFactory())
        label_not_owned = UserSupplementLabelFactory(user_supplement=user_supplement)
        line = PLSOrderLineFactory(store_id=order.store_id,
                                   store_order_id=order.store_order_id,
                                   pls_order=order,
                                   label=label_not_owned)
        r = self.client.get(f'/api/supplements/order-line-info?item_id={line.id}')
        self.assertEqual(r.status_code, 403)


class BillingInfoTestCase(PLSBaseTestCase):
    def setUp(self):
        super().setUp()

        self.user.profile.plan = GroupPlanFactory(title='Dropified Black', slug='black')
        self.user.profile.plan.permissions.add(AppPermissionFactory(name='pls_admin.use', description='PLS Admin'))
        self.user.profile.plan.save()
        self.user.profile.save()

    def test_info_success(self):
        self.client.force_login(self.user)
        AuthorizeNetCustomer.objects.create(user=self.user)

        response = self.client.get('/api/supplements/billing-info')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['success'], 1)

    def test_info_error(self):
        self.client.force_login(self.user)

        response = self.client.get('/api/supplements/billing-info')
        self.assertEqual(response.status_code, 200)
        # TODO: AUTHNET ROLLBACK
        # self.assertEqual(response.json()['error'], 1)
