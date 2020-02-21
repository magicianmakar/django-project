import base64
import json
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.shortcuts import reverse

from leadgalaxy.tests.factories import ShopifyStoreFactory, UserFactory
from lib.test import BaseTestCase
from shopify_orders.models import ShopifyOrderLog
from supplements.models import UserSupplementImage, UserSupplementLabel

from .factories import LabelSizeFactory, PLSOrderFactory, PLSOrderLineFactory, PLSupplementFactory, UserSupplementFactory, UserSupplementLabelFactory


class PLSBaseTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.label_size = LabelSizeFactory.create(
            slug='any-slug-123',
            height='2.25',
            width='5.75',
        )

        self.supplement = PLSupplementFactory.create(
            title='Fish Oil',
            description='Fish oil is great',
            category='supplement',
            tags='supplement',
            cost_price='15.99',
            label_template_url='http://example.com',
            wholesale_price='5.99',
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

    def get_url(self):
        raise NotImplementedError

    def do_test_login(self):
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 302)

    def do_test_get(self):
        self.client.force_login(self.user)
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)
        return response.content.decode()


class IndexTestCase(PLSBaseTestCase):
    def get_url(self):
        return reverse('pls:index')

    def test_login(self):
        self.do_test_login()

    def test_get(self):
        self.client.force_login(self.user)

        PLSupplementFactory.create(
            title='Fish Oil 2',
            description='Fish oil is great',
            category='supplement',
            tags='supplement',
            cost_price='15.99',
            wholesale_price='5.99',
            label_template_url='http://example.com',
        )

        content = self.do_test_get()
        self.assertEqual(content.count("product-imitation"), 2)


class SupplementTestCase(PLSBaseTestCase):
    def get_url(self):
        kwargs = {'supplement_id': self.supplement.id}
        return reverse('pls:supplement', kwargs=kwargs)

    def test_login(self):
        self.do_test_login()

    def test_get(self):
        content = self.do_test_get()
        self.assertIn(self.user_supplement.title, content)

    def test_post_error(self):
        self.client.force_login(self.user)
        data = dict(
            action="save",
        )
        response = self.client.post(self.get_url(), data=data)
        self.assertEqual(response.status_code, 200)

    def test_get_new(self):
        self.client.force_login(self.user)

        new_supplement = PLSupplementFactory.create(
            title='Fish Oil',
            description='Fish oil is great',
            category='supplement',
            tags='supplement',
            cost_price='15.99',
            wholesale_price='5.99',
            label_template_url='http://example.com',
        )

        kwargs = {'supplement_id': new_supplement.id}
        url = reverse('pls:supplement', kwargs=kwargs)

        self.assertEqual(new_supplement.user_pl_supplements.count(), 0)
        response = self.client.get(url)
        self.assertIn(new_supplement.title, response.content.decode())
        self.assertEqual(new_supplement.user_pl_supplements.count(), 0)

    def test_post_save(self):
        self.client.force_login(self.user)
        image = open('app/static/aliex.png', 'rb')
        data = dict(
            action="save",
            title="New title",
            description="New description",
            category=self.user_supplement.category,
            tags=self.user_supplement.tags,
            price=self.user_supplement.price,
            compare_at_price=self.user_supplement.compare_at_price,
            cost_price=self.user_supplement.pl_supplement.cost_price,
            shipstation_sku='test-sku',
            upload=image,
        )

        with patch('product_common.lib.views.aws_s3_upload',
                   return_value='http://example.com/test'):
            self.assertEqual(self.user.pl_supplements.count(), 1)
            self.assertEqual(UserSupplementImage.objects.count(), 0)
            response = self.client.post(self.get_url(), data=data)

            self.assertEqual(response.status_code, 302)

            detail = self.client.get(response.url)
            content = detail.content.decode()
            key = ('<input type="text" name="tags" '
                   'value="supplement" class="form-control" '
                   'required id="id_tags" />')
            self.assertIn(key, content)
            image.close()
            self.assertEqual(self.user.pl_supplements.count(), 2)
            self.assertEqual(UserSupplementImage.objects.count(), 1)

            # Test without image.
            del data['upload']
            response = self.client.post(self.get_url(), data=data)
            self.assertEqual(self.user.pl_supplements.count(), 3)
            self.assertEqual(UserSupplementImage.objects.count(), 1)

    def test_post_approve_error(self):
        self.client.force_login(self.user)
        data = dict(
            action="approve",
            title="New title",
            description="New description",
            category=self.user_supplement.category,
            tags=self.user_supplement.tags,
            price=self.user_supplement.price,
            compare_at_price=self.user_supplement.compare_at_price,
            cost_price=self.user_supplement.pl_supplement.cost_price,
            shipstation_sku='test-sku',
        )

        with patch('product_common.lib.views.aws_s3_upload',
                   return_value='http://example.com/test'):
            response = self.client.post(self.get_url(), data=data)
            self.assertEqual(response.status_code, 200)
            self.assertIn("Label is required", response.content.decode())

    def test_post_approve(self):
        self.client.force_login(self.user)
        image = open('app/static/example-label.pdf', 'rb')
        img = 'app/static/pls-mockup/SevenLimb_29033-2_VytaMind_60_200cc.png'
        with open(img, 'rb') as reader:
            data = base64.b64encode(reader.read()).decode()
            image_data_url = f'data:image/png;base64,{data}'

        data = dict(
            action="approve",
            title="New title",
            description="New description",
            category=self.user_supplement.category,
            tags=self.user_supplement.tags,
            price=self.user_supplement.price,
            compare_at_price=self.user_supplement.compare_at_price,
            cost_price=self.user_supplement.pl_supplement.cost_price,
            shipstation_sku='test-sku',
            upload=image,
            image_data_url=image_data_url,
        )

        with patch('product_common.lib.views.aws_s3_upload',
                   return_value='http://example.com/test'):
            self.assertEqual(UserSupplementImage.objects.count(), 0)
            self.assertEqual(UserSupplementLabel.objects.all().count(), 1)
            response = self.client.post(self.get_url(), data=data)
            url = reverse('pls:my_labels') + "?s=1"
            self.assertRedirects(response, url)
            self.assertEqual(self.user.pl_supplements.count(), 2)
            self.assertEqual(UserSupplementImage.objects.count(), 1)
            self.assertEqual(UserSupplementLabel.objects.all().count(), 2)

            image.close()


class MySupplementsTestCase(PLSBaseTestCase):
    def get_url(self):
        return reverse('pls:my_supplements')

    def test_login(self):
        self.do_test_login()

    def test_get(self):
        content = self.do_test_get()
        self.assertEqual(content.count("product-imitation"), 1)


class MyLabelsTestCase(PLSBaseTestCase):
    def get_url(self):
        return reverse('pls:my_labels')

    def test_login(self):
        self.do_test_login()

    def test_get(self):
        content = self.do_test_get()
        self.assertIn("Found 1 label.", content)


class AllLabelsTestCase(PLSBaseTestCase):
    def get_url(self):
        return reverse('pls:all_labels')

    def test_login(self):
        self.do_test_login()

    def test_get(self):
        content = self.do_test_get()
        self.assertIn("Found 1 label.", content)


class LabelDetailTestCase(PLSBaseTestCase):
    def get_url(self):
        kwargs = {'label_id': self.label.id}
        return reverse('pls:label_detail', kwargs=kwargs)

    def test_login(self):
        self.do_test_login()

    def test_get(self):
        content = self.do_test_get()
        self.assertIn(self.label.label_id_string, content)

    def test_post_comment(self):
        self.client.force_login(self.user)
        data = dict(
            action="comment",
            comment="New comment",
        )

        self.assertEqual(self.label.comments.count(), 0)
        response = self.client.post(self.get_url(), data=data)
        self.assertRedirects(response, self.get_url())
        self.assertEqual(self.label.comments.count(), 1)

    def test_post_approve(self):
        self.client.force_login(self.user)
        data = dict(
            action=self.label.APPROVED,
        )

        mock_response = MagicMock()
        with open('app/static/example-label.pdf', 'rb') as reader:
            mock_response.content = reader.read()

        return_urls = [
            'http://example.com/test.pdf',
            'http://example.com/test.jpg',
        ]

        with patch('product_common.lib.views.aws_s3_upload',
                   side_effect=return_urls), \
                patch('requests.get', return_value=mock_response):
            self.assertEqual(self.label.comments.count(), 0)
            response = self.client.post(self.get_url(), data=data)
            self.assertRedirects(response, self.get_url())
            self.assertEqual(self.label.comments.count(), 1)

            self.label.refresh_from_db()
            self.assertTrue(self.label.url.endswith('pdf'))

    def test_post_error(self):
        self.client.force_login(self.user)
        data = dict(
            action="error",
        )

        self.assertEqual(self.label.comments.count(), 0)
        response = self.client.post(self.get_url(), data=data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.label.comments.count(), 0)


class OrdersShippedWebHookTestCase(BaseTestCase):
    def setup_data(self):
        order_key = 'key'
        store_type = 'shopify'
        order_id = '1234'
        line_id = '5678'

        line_key = 'line-key'

        self.shipments = [{
            'orderKey': order_key,
            'trackingNumber': 'tracking-number',
            'shipmentItems': [{'lineItemKey': line_key}],
        }]

        self.url = reverse('pls:order_shipped_webhook')

        self.data = {
            'resource_url': 'fake',
            'resource_type': 'SHIP_NOTIFY',
        }

        self.store = ShopifyStoreFactory(primary_location=12)
        store_id = self.store.id

        self.pls_order = PLSOrderFactory(shipstation_key=order_key,
                                         store_type=store_type,
                                         store_id=store_id,
                                         store_order_id=order_id)

        self.pls_order_line = PLSOrderLineFactory(shipstation_key=line_key,
                                                  store_id=store_id,
                                                  store_order_id=order_id,
                                                  line_id=line_id,
                                                  pls_order=self.pls_order)

    def test_post(self):
        self.setup_data()

        with patch('product_common.views.get_shipstation_shipments') as mock_func, \
                patch('requests.post'):
            mock_func.return_value = self.shipments
            response = self.client.post(self.url,
                                        data=json.dumps(self.data),
                                        content_type='application/json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ShopifyOrderLog.objects.count(), 1)


class ProductTestCase(PLSBaseTestCase):
    def get_url(self):
        return reverse('pls:product')

    def test_login(self):
        self.do_test_login()

    def test_get(self):
        self.client.force_login(self.user)
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)

    def test_post_error(self):
        self.client.force_login(self.user)
        response = self.client.post(self.get_url())
        self.assertEqual(response.status_code, 200)

    def test_post(self):
        self.client.force_login(self.user)
        data = dict(
            title="New title",
            description="New description",
            category=self.user_supplement.category,
            tags=self.user_supplement.tags,
            shipstation_sku='test-sku',
            cost_price='20.00',
            wholesale_price='10.00',
            label_size=self.label_size.id,
            template=open('app/static/example-label.pdf', 'rb'),
            thumbnail=open('app/static/aliex.png', 'rb'),
            product_information='New Information',
            authenticity_certificate=open('app/static/example-label.pdf', 'rb'),
        )
        with patch('product_common.lib.views.aws_s3_upload',
                   return_value='http://example.com/test'):
            response = self.client.post(self.get_url(), data=data)
            self.assertRedirects(response, reverse('pls:index'))


class OrderListTestCase(PLSBaseTestCase):
    def get_url(self):
        return reverse('pls:order_list')

    def test_login(self):
        self.do_test_login()

    def test_get(self):
        self.client.force_login(self.user)
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)


class PayoutListTestCase(PLSBaseTestCase):
    def get_url(self):
        return reverse('pls:payout_list')

    def test_login(self):
        self.do_test_login()

    def test_get(self):
        self.client.force_login(self.user)
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)


class UserSupplementViewTestCase(PLSBaseTestCase):
    def setUp(self):
        super().setUp()

        old_title = self.old_title = 'Old title'
        self.new_user_supplement = UserSupplementFactory.create(
            title=old_title,
            description=self.supplement.description,
            category=self.supplement.category,
            tags=self.supplement.tags,
            user=self.user,
            pl_supplement=self.supplement,
            price="15.99",
            compare_at_price="20.00",
        )

    def get_url(self):
        kwargs = {'supplement_id': self.new_user_supplement.id}
        return reverse('pls:user_supplement', kwargs=kwargs)

    def test_login(self):
        self.do_test_login()

    def test_get(self):
        self.client.force_login(self.user)
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)

    def test_post(self):
        self.client.force_login(self.user)

        new_title = 'New title'

        user_supplement = self.new_user_supplement

        data = dict(
            title=new_title,
            description=user_supplement.description,
            category=user_supplement.category,
            tags=user_supplement.tags,
            shipstation_sku='test-sku',
            price=user_supplement.price,
            compare_at_price=user_supplement.compare_at_price,
            cost_price=user_supplement.cost_price,
            action='save',
        )

        self.assertEqual(self.user.pl_supplements.count(), 2)
        response = self.client.post(self.get_url(), data=data)
        self.assertEqual(self.user.pl_supplements.count(), 2)
        self.assertRedirects(response, self.get_url())

        user_supplement.refresh_from_db()
        self.assertTrue(user_supplement.title, new_title)


class BillingTestCase(PLSBaseTestCase):
    def get_url(self):
        return reverse('pls:billing')

    def test_login(self):
        self.do_test_login()

    def test_get(self):
        self.client.force_login(self.user)
        content = self.do_test_get()
        self.assertIn('Credit Card', content)

    @patch('supplements.mixin.get_customer_payment_profile')
    @patch('supplements.lib.authorizenet.createCustomerProfileController')
    @patch('supplements.lib.authorizenet.createCustomerPaymentProfileController')
    @patch('supplements.lib.authorizenet.apicontractsv1')
    def test_post(self,
                  mock_apicontractsv1,
                  mock_payment_controller,
                  mock_profile_controller,
                  mock_payment_profile):
        self.client.force_login(self.user)

        mock_response = MagicMock()
        mock_response.customerPaymentProfileId = 2

        mock_controller = MagicMock()
        mock_controller.getresponse.return_value = mock_response

        mock_payment_controller.return_value = mock_controller

        mock_response.messages.resultCode = 'Ok'
        mock_response.customerProfileId = 1

        mock_controller = MagicMock()
        mock_controller.getresponse.return_value = mock_response

        mock_profile_controller.return_value = mock_controller

        cc_number = '1' * 16

        mock_profile = MagicMock()
        mock_profile.payment.creditCard = cc_number

        mock_payment_profile.return_value = mock_profile

        data = {
            'cc-name': self.user.get_full_name(),
            'cc-number': cc_number,
            'cc-exp': '12/2020',
            'cc-cvc': '123',
            'address_line1': 'Test address',
            'address_city': 'City',
            'address_state': 'State',
            'address_zip': '12345',
            'address_country': 'USA',
        }

        response = self.client.post(self.get_url(), data=data)
        self.assertRedirects(response, self.get_url())

        self.assertEqual(self.user.authorize_net_customer.customer_id, '1')
        self.assertEqual(self.user.authorize_net_customer.payment_id, '2')

    @patch('supplements.mixin.get_customer_payment_profile')
    @patch('supplements.lib.authorizenet.createCustomerProfileController')
    @patch('supplements.lib.authorizenet.createCustomerPaymentProfileController')
    @patch('supplements.lib.authorizenet.apicontractsv1')
    def test_post_error(self,
                        mock_apicontractsv1,
                        mock_payment_controller,
                        mock_profile_controller,
                        mock_payment_profile):
        self.client.force_login(self.user)

        mock_response = MagicMock()
        mock_response.customerPaymentProfileId = 2

        mock_controller = MagicMock()
        mock_controller.getresponse.return_value = mock_response

        mock_payment_controller.return_value = mock_controller

        mock_response = MagicMock()
        message_text = 'A duplicate record with ID 1 already exists.'

        mock_response.messages.resultCode = 'ERROR'
        mock_response.messages.message[0]['text'].text = message_text

        mock_controller = MagicMock()
        mock_controller.getresponse.return_value = mock_response

        mock_profile_controller.return_value = mock_controller

        cc_number = '1' * 16

        mock_profile = MagicMock()
        mock_profile.payment.creditCard = cc_number

        mock_payment_profile.return_value = mock_profile

        data = {
            'cc-name': self.user.get_full_name(),
            'cc-number': cc_number,
            'cc-exp': '12/2020',
            'cc-cvc': '123',
            'address_line1': 'Test address',
            'address_city': 'City',
            'address_state': 'State',
            'address_zip': '12345',
            'address_country': 'USA',
        }

        response = self.client.post(self.get_url(), data=data)
        self.assertEqual(response.status_code, 200)


class UploadJSONTestCase(PLSBaseTestCase):
    def get_url(self):
        return reverse('pls:upload_json')

    def test_login(self):
        self.do_test_login()

    def test_get(self):
        self.client.force_login(self.user)
        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, 200)

    def test_post_error(self):
        self.client.force_login(self.user)
        response = self.client.post(self.get_url())
        self.assertEqual(response.status_code, 200)

    def test_post(self):
        self.client.force_login(self.user)

        test_file = 'supplements/tests/assets/supplements.json'
        upload_file = open(test_file, 'rb')
        file_dict = {'upload': SimpleUploadedFile(upload_file.name, upload_file.read())}

        response = self.client.post(self.get_url(), data=file_dict)
        self.assertRedirects(response, reverse('pls:index'))


class DownloadJSONTestCase(PLSBaseTestCase):
    def get_url(self):
        return reverse('pls:download_json')

    def test_get(self):
        self.client.force_login(self.user)
        response = self.client.get(self.get_url())

        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content)
        self.assertEqual(content[0]['title'], 'Fish Oil')
