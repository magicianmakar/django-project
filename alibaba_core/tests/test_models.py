from unittest.mock import patch

from leadgalaxy.tests.factories import UserFactory
from lib.test import BaseTestCase

from . import mock_data
from .factories import AlibabaAccountFactory


class AlibabaAccountTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.alibaba_account = AlibabaAccountFactory(
            user=self.user,
            access_token='test_access_token',
            alibaba_user_id='1234567',
        )

        self.client.login(
            username=self.user.username,
            password=self.password
        )

    @patch('alibaba_core.utils.APIRequest.post')
    def test_get_product(self, mock_post):
        mock_post.return_value = mock_data.product_get_response

        product = self.alibaba_account.get_product(1600124642247)

        self.assertEqual(product['id'], 1600124642247)
        self.assertEqual(product['price'], '6.90')
        self.assertEqual(product['original_url'], 'https://www.alibaba.com/product-detail/1600124642247.html')
        self.assertEqual(product['store']['name'], 'Alibaba')
        self.assertEqual(product['store']['id'], '634215')

    @patch('alibaba_core.utils.APIRequest.post')
    def test_create_order(self, mock_post):
        mock_post.return_value = mock_data.create_order_response

        order_data = {
            'shipping_address': {
                'zip': '12345',
                'country': 'United States',
                'address1': '123 Sea View Drive',
                'address2': '123 Sea View Drive',
                'city': 'New York',
                'first_name': 'James',
                'phone': {
                    'country': '01',
                    'number': '123456789',
                },
            },
            'order': {
                'note': 'Test',
            }
        }

        alibaba_order_id = self.alibaba_account.create_order(order_data)

        self.assertEqual(alibaba_order_id, '100006192')

    @patch('alibaba_core.utils.APIRequest.post')
    def test_get_shipping_costs(self, mock_post):
        mock_post.return_value = mock_data.get_shipping_cost_response

        shippings = self.alibaba_account.get_shipping_costs(1600118556060, 3, 'US')

        self.assertEqual(shippings[0]['shipping_type'], 'EXPRESS')
        self.assertEqual(shippings[0]['destination_country'], 'US')
        self.assertEqual(shippings[0]['fee']['amount'], '20')

    @patch('alibaba_core.utils.APIRequest.post')
    def test_get_order_payments(self, mock_post):
        mock_post.return_value = mock_data.get_order_payments_response

        payments = self.alibaba_account.get_order_payments('100006199')

        fund_pay = payments['fund_pay_list']['fund_pay'][0]
        refund = payments['refund_list']['refund'][0]

        self.assertEqual(fund_pay['pay_amount']['amount'], '12.00')
        self.assertEqual(fund_pay['receive_amount']['amount'], '12.00')
        self.assertEqual(payments['service_fee']['amount'], '1.00')
        self.assertEqual(refund['id'], 123432)
        self.assertEqual(refund['amount']['amount'], '2.00')
