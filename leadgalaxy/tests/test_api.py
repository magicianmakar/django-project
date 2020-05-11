from django.core import mail
import json
import uuid
from datetime import timedelta

import arrow
from munch import Munch
from unittest.mock import patch, Mock, PropertyMock

from django.test import override_settings
from django.utils import timezone
from django.core.cache import caches
from last_seen.models import LastSeen

from . import factories as f
from lib.test import BaseTestCase
from shopified_core.utils import order_data_cache


class ProductsApiTestCase(BaseTestCase):
    def setUp(self):
        self.parent_user = f.UserFactory()
        self.user = f.UserFactory()
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.store = f.ShopifyStoreFactory(user=self.user)
        self.client.login(username=self.user.username, password=self.password)

    @patch('shopified_core.mixins.ApiResponseMixin.get_user')
    def test_find_products_by_shopify_ids(self, get_api_user):
        get_api_user.return_value = self.user
        product = f.ShopifyProductFactory(store=self.store, user=self.user, shopify_id=12345678)
        data = {'store': self.store.id, 'product': product.shopify_id}

        r = self.client.get('/api/find-products', data, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        json_response = json.loads(r.content)
        self.assertIsNotNone(json_response.get(str(product.shopify_id)))

    @patch('shopified_core.mixins.ApiResponseMixin.get_user')
    def test_find_products_by_aliexpress_ids(self, get_api_user):
        get_api_user.return_value = self.user
        source_id = 123
        product = f.ShopifyProductFactory(store=self.store, user=self.user, shopify_id=12345678)
        product_url = 'aliexpress.com/{}.html'.format(source_id)
        supplier = f.ProductSupplierFactory(store=self.store, product=product, supplier_name='Test', product_url=product_url)
        data = {'store': self.store.id, 'aliexpress': supplier.source_id}

        r = self.client.get('/api/find-products', data)
        self.assertEqual(r.status_code, 200)
        json_response = json.loads(r.content)
        self.assertIsNotNone(json_response.get(str(source_id)))

    @patch('leadgalaxy.tasks.update_shopify_product')
    @patch('leadgalaxy.tasks.update_product_connection.delay')
    def test_post_product_connect(self, update_product_connection, update_shopify_product):
        product = f.ShopifyProductFactory(
            store=self.store, user=self.user, shopify_id=12345678,
            data='''{"store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item/12345467890.html"
            }}''')

        data = {'product': product.id, 'store': self.store.id, 'shopify': 12345670001}
        r = self.client.post('/api/shopify/product-connect', data)
        self.assertEqual(r.status_code, 200)

        product.refresh_from_db()
        self.assertEqual(product.shopify_id, data['shopify'])

        update_product_connection.assert_called_with(self.store.id, data['shopify'])
        update_shopify_product.assert_called_with(self.store.id, data['shopify'], product_id=product.id)

    @patch('leadgalaxy.utils.duplicate_product')
    def test_post_product_duplicate(self, duplicate_product):
        duplicate_product_id = 1111222
        duplicate_product.return_value = Munch({'id': duplicate_product_id})
        product = f.ShopifyProductFactory(
            store=self.store, user=self.user, shopify_id=12345678,
            data='''{"store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item/12345467890.html"
            }}''')

        data = {'product': product.id}
        r = self.client.post('/api/shopify/product-duplicate', data)
        self.assertEqual(r.status_code, 200)

        self.assertEqual(r.json()['product']['id'], duplicate_product_id)
        self.assertEqual(r.json()['product']['url'], f'/product/{duplicate_product_id}')

        duplicate_product.assert_called_with(product)

    @patch('leadgalaxy.utils.set_shopify_order_note')
    def test_post_order_note(self, set_shopify_order_note):
        order_id = '123456789'
        note = 'Test Note'
        data = {'store': self.store.id, 'order_id': order_id, 'note': note}

        r = self.client.post('/api/shopify/order-note', data)
        self.assertEqual(r.status_code, 200)

        set_shopify_order_note.assert_called_with(self.store, order_id, note)

    @patch('leadgalaxy.tasks.create_image_zip.apply_async')
    def test_get_product_image_download(self, create_image_zip):
        product = f.ShopifyProductFactory(
            store=self.store, user=self.user, shopify_id=12345678,
            data='''{"store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item/12345467890.html"
            }}''')

        data = {'product': product.id}

        r = self.client.get('/api/shopify/product-image-download', data)
        self.assertEqual(r.status_code, 422)
        self.assertIn(r.json()['error'], 'Product doesn\'t have any images')

        create_image_zip.assert_not_called()

        images = ["http://www.aliexpress.com/image/1.png"]
        product = f.ShopifyProductFactory(
            store=self.store, user=self.user, shopify_id=12345678,
            data=json.dumps({"images": images}))

        data = {'product': product.id}
        r = self.client.get('/api/shopify/product-image-download', data)
        self.assertEqual(r.status_code, 200)

        create_image_zip.assert_called_with(args=[images, product.id], countdown=5)

    def test_get_order_data(self):
        store_id, order_id, line_id = self.store.id, 1233, 55466677
        order_key = f'{store_id}_{order_id}_{line_id}'

        data = {
            "id": order_key,
            "quantity": 1,
            "shipping_address": {
                "first_name": "Red",
                "address1": "5541 Great Road ",
                "phone": "922481541",
                "city": "Moody",
                "zip": "35004",
                "province": "Alabama",
                "country": "United States",
                "last_name": "Smin",
                "address2": "",
                "company": "",
                "name": "Red Smin",
                "country_code": "US",
                "province_code": "AL"
            },
            "order_id": order_id,
            "line_id": line_id,
            "product_id": 686,
            "source_id": 32846904328,
            "supplier_id": 1405349,
            "supplier_type": "aliexpress",
            "total": 26.98,
            "store": store_id,
            "order": {"phone": "922481541", "note": "Do not put invoice.", "epacket": True, "auto_mark": True, "phoneCountry": "+1"},
            "products": [],
            "is_bundle": False,
            "variant": [{"sku": "sku-1-193", "title": "black"}, {"sku": "sku-2-201336106", "title": "United States"}],
            "ordered": False,
            "fast_checkout": True,
            "solve": True
        }

        caches['orders'].set(f'order_{order_key}', data)
        self.assertIsNotNone(caches['orders'].get(f'order_{order_key}'))
        self.assertIsNotNone(order_data_cache(f'order_{order_key}'))
        self.assertIsNotNone(order_data_cache(f'{order_key}'))
        self.assertIsNotNone(order_data_cache(self.store.id, order_id, line_id))

        # Store not found
        r = self.client.get('/api/shopify/order-data', {'order': f'444{order_key}'})
        self.assertEqual(r.status_code, 404)
        self.assertIn('Store not found', r.content.decode())

        # Order not found
        r = self.client.get('/api/shopify/order-data', {'order': f'{order_key}5455'})
        self.assertEqual(r.status_code, 404)
        self.assertIn('Not found:', r.content.decode())

        # Key order prefix is present
        r = self.client.get('/api/shopify/order-data', {'order': f'order_{order_key}'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(json.dumps(r.json(), indent=2), json.dumps(data, indent=2))

        # Key prefix removed (default)
        r = self.client.get('/api/shopify/order-data', {'order': f'{order_key}'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), data)
        self.assertFalse(r.json()['ordered'])

        # Test aliexpress_country_code_map
        data['shipping_address']['country_code'] = 'GB'
        caches['orders'].set(f'order_{order_key}', data)

        r = self.client.get('/api/shopify/order-data', {'order': f'{order_key}'})
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.json()['shipping_address']['country_code'], data['shipping_address']['country_code'])
        self.assertEqual(r.json()['shipping_address']['country_code'], 'UK')

        # Order Track exist
        f.ShopifyOrderTrackFactory(user=self.user, store=self.store, order_id=order_id, line_id=line_id)

        r = self.client.get('/api/shopify/order-data', {'order': f'{order_key}'})
        ordered = r.json()['ordered']
        self.assertEqual(r.status_code, 200)
        self.assertEqual(type(ordered), dict)
        self.assertIn('time', ordered)
        self.assertIn('link', ordered)

    def test_post_variants_mapping(self):
        product = f.ShopifyProductFactory(
            store=self.store, user=self.user, shopify_id=12345678,
            data='''{"store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item/12345467890.html"
            }}''')

        supplier = f.ProductSupplierFactory(product=product)

        var_id = '18395643215934'
        data = {
            'product': product.id,
            'supplier': supplier.id,
            var_id: '[{"title":"China","sku":"sku-1-201336100"}]',
        }

        r = self.client.post('/api/shopify/variants-mapping', data)
        self.assertEqual(r.status_code, 200)

        product.refresh_from_db()
        self.assertEqual(product.get_variant_mapping(var_id), json.loads(data[var_id]))
        self.assertEqual(product.get_variant_mapping(var_id, for_extension=True), json.loads(data[var_id]))

    def test_post_suppliers_mapping(self):
        product = f.ShopifyProductFactory(
            store=self.store, user=self.user, shopify_id=12345678,
            data='''{"store": {
                "name": "Suplier 1",
                "url": "https://www.aliexpress.com/item/12345467890.html"
            }}''')

        supplier1 = f.ProductSupplierFactory(product=product)
        supplier2 = f.ProductSupplierFactory(product=product)

        product.set_default_supplier(supplier1)

        var_ids = ['18401388822590', '18401388888126', '18401388855358']
        data = {
            'config': 'default',
            'product': product.id,
            f'shipping_{supplier1.id}_{var_ids[0]}': '[{"country":"FR","method":"FEDEX_IE","country_name":"France","method_name":"Fedex IE ($51.38)"},{"country":"US","method":"EMS","country_name":"United States","method_name":"EMS ($32.14)"}]', # noqa
            f'shipping_{supplier1.id}_{var_ids[1]}': '[{"country":"CA","method":"EMS","country_name":"Canada","method_name":"EMS ($37.49)"}]', # noqa
            f'shipping_{supplier1.id}_{var_ids[2]}': '[{"country_name":"United States","country":"US","method_name":"Fedex IE ($40.53)","method":"FEDEX_IE"}]', # noqa
            f'{var_ids[0]}': '{"supplier":' f'{supplier1.id}' ',"shipping":[{"country":"FR","method":"FEDEX_IE","country_name":"France","method_name":"Fedex IE ($51.38)"},{"country":"US","method":"EMS","country_name":"United States","method_name":"EMS ($32.14)"}]}', # noqa
            f'{var_ids[1]}': '{"supplier":' f'{supplier1.id}' ',"shipping":[{"country":"CA","method":"EMS","country_name":"Canada","method_name":"EMS ($37.49)"}]}', # noqa
            f'{var_ids[2]}': '{"supplier":' f'{supplier1.id}' ',"shipping":[{"country_name":"United States","country":"US","method_name":"Fedex IE ($40.53)","method":"FEDEX_IE"}]}', # noqa
            f'variant_{supplier1.id}_{var_ids[0]}': '[{"sku":"sku-1-173","title":"blue"},{"sku":"sku-2-201336106","title":"United States"}]',
            f'variant_{supplier1.id}_{var_ids[1]}': '[{"sku":"sku-1-366","title":"yellow"},{"sku":"sku-2-201336106","title":"United States"}]',
            f'variant_{supplier1.id}_{var_ids[2]}': '[{"sku":"sku-1-193","title":"black"},{"sku":"sku-2-201336106","title":"United States"}]',
            f'variant_{supplier2.id}_{var_ids[0]}': '[{"sku":"sku-1-201336100","title":"China"},{"sku":"sku-2-193","title":"black"},{"sku":"sku-3-100006192","title":"2"},{"sku":"sku-4-203221828","title":"Player Sets"}]', # noqa
            f'variant_{supplier2.id}_{var_ids[1]}': '[{"sku":"sku-1-201336100","title":"China"},{"sku":"sku-2-193","title":"black"},{"sku":"sku-3-100006192","title":"2"},{"sku":"sku-4-203221828","title":"Player Sets"}]', # noqa
            f'variant_{supplier2.id}_{var_ids[2]}': '[{"sku":"sku-1-201336100","title":"China"},{"sku":"sku-2-193","title":"black"},{"sku":"sku-3-100006192","title":"2"},{"sku":"sku-4-203221828","title":"Player Sets"}]', # noqa
        }

        r = self.client.post('/api/shopify/suppliers-mapping', data)
        self.assertEqual(r.status_code, 200)

        product.refresh_from_db()
        supplier1.refresh_from_db()
        supplier2.refresh_from_db()

        self.assertEqual(product.get_variant_mapping(var_ids[0], supplier=supplier1), json.loads(data[f'variant_{supplier1.id}_{var_ids[0]}']))
        self.assertEqual(product.get_variant_mapping(var_ids[1], supplier=supplier1), json.loads(data[f'variant_{supplier1.id}_{var_ids[1]}']))
        self.assertEqual(product.get_variant_mapping(var_ids[2], supplier=supplier1), json.loads(data[f'variant_{supplier1.id}_{var_ids[2]}']))

        self.assertEqual(product.get_variant_mapping(var_ids[0], supplier=supplier2), json.loads(data[f'variant_{supplier2.id}_{var_ids[0]}']))
        self.assertEqual(product.get_variant_mapping(var_ids[1], supplier=supplier2), json.loads(data[f'variant_{supplier2.id}_{var_ids[1]}']))
        self.assertEqual(product.get_variant_mapping(var_ids[2], supplier=supplier2), json.loads(data[f'variant_{supplier2.id}_{var_ids[2]}']))

        shipping = product.get_shipping_for_variant(supplier_id=supplier1.id, variant_id=var_ids[0], country_code='MA')
        self.assertIsNone(shipping)

        shipping = product.get_shipping_for_variant(supplier_id=supplier1.id, variant_id=var_ids[0], country_code='FR')
        self.assertEqual(shipping['country'], 'FR')
        self.assertEqual(shipping['method'], 'FEDEX_IE')

        shipping = product.get_shipping_for_variant(supplier_id=supplier1.id, variant_id=var_ids[0], country_code='US')
        self.assertEqual(shipping['country'], 'US')
        self.assertEqual(shipping['method'], 'EMS')

        shipping = product.get_shipping_for_variant(supplier_id=supplier1.id, variant_id=var_ids[1], country_code='CA')
        self.assertEqual(shipping['country'], 'CA')
        self.assertEqual(shipping['method'], 'EMS')
        self.assertEqual(shipping['method_name'], 'EMS ($37.49)')

        shipping = product.get_shipping_for_variant(supplier_id=supplier1.id, variant_id=var_ids[2], country_code='US')
        self.assertEqual(shipping['country'], 'US')
        self.assertEqual(shipping['method'], 'FEDEX_IE')

    def test_get_order_fulfill_active(self):
        self.user.profile.plan.permissions.add(f.AppPermissionFactory(name='orders.use', description=''))

        r = self.client.get('/api/shopify/order-fulfill', {})
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.json()['error'], 'User is not active')

    @patch('last_seen.models.LastSeen.objects.when', Mock(return_value=True))
    def test_get_order_fulfill(self):
        self.user.profile.plan.permissions.add(f.AppPermissionFactory(name='orders.use', description=''))

        f.ShopifyOrderTrackFactory(store=self.store, user=self.user, order_id=12345, line_id=777777)
        track = f.ShopifyOrderTrackFactory(store=self.store, user=self.user, order_id=12346, line_id=777778)
        track.created_at = arrow.utcnow().replace(days=-2).datetime
        track.save()

        r = self.client.get('/api/shopify/order-fulfill', {})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 2)

        r = self.client.get('/api/shopify/order-fulfill', {'count_only': 'true'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['pending'], 2)

        track = f.ShopifyOrderTrackFactory(store=self.store, user=self.user, order_id=12347, line_id=777779)
        track.created_at = arrow.utcnow().replace(days=-3).datetime
        track.save()

        r = self.client.get('/api/shopify/order-fulfill', {})
        self.assertEqual(len(r.json()), 3)

        date = arrow.utcnow().replace(days=-2).datetime
        r = self.client.get('/api/shopify/order-fulfill', {'created_at': f'{date:%m/%d/%Y-}'})
        self.assertEqual(len(r.json()), 2)

        from_date, to_date = arrow.utcnow().replace(days=-3).datetime, arrow.utcnow().replace(days=-3).datetime
        r = self.client.get('/api/shopify/order-fulfill', {'created_at': f'{from_date:%m/%d/%Y}-{to_date:%m/%d/%Y}'})
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]['id'], track.id)

    @patch('leadgalaxy.tasks.update_shopify_order.apply_async')
    def test_delete_order_fulfill(self, update_shopify_order):
        track = f.ShopifyOrderTrackFactory(user=self.user, store=self.store)
        order = f.ShopifyOrderFactory(user=self.user, store=self.store, order_id=track.order_id, need_fulfillment=0)
        line = f.ShopifyOrderLineFactory(order=order)
        line.track = track
        line.save()

        r = self.client.delete(f'/api/shopify/order-fulfill?order_id={track.order_id}&line_id={track.line_id}')
        self.assertEqual(r.status_code, 200)

        # ShopifyOrderLog created
        self.assertEqual(self.store.shopifyorderlog_set.count(), 1)

        # OrderTrack doesn't exist
        self.assertFalse(self.store.shopifyordertrack_set.exists())

        # ShopifyOrder
        update_shopify_order.assert_called_with(args=[self.store.id, track.order_id], kwargs={'from_webhook': False})
        # order.refresh_from_db()
        # self.assertEqual(order.need_fulfillment, 1)

        # Empty search params
        r = self.client.delete('/api/shopify/order-fulfill')
        self.assertEqual(r.status_code, 404)

    @patch('leadgalaxy.models.ShopifyStore.get_link', Mock(return_value=''))
    @patch('leadgalaxy.models.ShopifyStore.get_primary_location', Mock(return_value=1))
    @patch('leadgalaxy.api.requests')
    def test_post_fulfill_order(self, requests_mock):
        requests_mock.post = Mock(return_value=Mock(raise_for_status=Mock(return_value=None)))

        track = f.ShopifyOrderTrackFactory(user=self.user, store=self.store)
        data = {
            'fulfill-store': self.store.id,
            'fulfill-line-id': track.line_id,
            'fulfill-order-id': track.order_id,
            'fulfill-traking-number': 123,
            'fulfill-location-id': 1
        }

        r = self.client.post('/api/shopify/fulfill-order', data)
        self.assertEqual(r.status_code, 200)
        # Call Shopify once
        requests_mock.post.assert_called_once()

        # ShopifyOrderLog created
        self.assertEqual(self.store.shopifyorderlog_set.count(), 1)

        # Already fulfilled
        requests_mock.post = Mock(return_value=Mock(
            raise_for_status=Mock(side_effect=Exception()),
            text='already fulfilled'
        ))
        r = self.client.post('/api/shopify/fulfill-order', data)

        self.assertEqual(r.status_code, 500)
        self.assertNotIn('Internal Server Error', r.json().get('error'))

    @patch('leadgalaxy.utils.get_shopify_order_line')
    def test_post_order_fulfill(self, get_shopify_order_line):
        track = f.ShopifyOrderTrackFactory(user=self.user, store=self.store)
        data = {
            'store': self.store.id,
            'order_id': track.order_id,
            'line_id': track.line_id,
            'line_sku': '',
            'aliexpress_order_id': '123',
            'source_type': 'aliexpress',
        }

        r = self.client.post('/api/shopify/order-fulfill', data)
        self.assertEqual(r.status_code, 200)

        # ShopifyOrderTrack updated
        track.refresh_from_db()
        self.assertEqual(track.source_id, data['aliexpress_order_id'])
        self.assertEqual(track.source_type, data['source_type'])

        # ShopifyOrderLog created
        self.assertEqual(self.store.shopifyorderlog_set.count(), 1)

        # Search line id by sku
        get_shopify_order_line.return_value = {'id': track.line_id, 'fulfillment_status': 'fulfilled'}
        r = self.client.post('/api/shopify/order-fulfill', {**data, 'line_sku': '123', 'line_id': ''}, HTTP_REFERER='https://oberlo.com')

        self.assertEqual(r.status_code, 200)
        get_shopify_order_line.assert_called_once()

        track.refresh_from_db()
        self.assertEqual(track.shopify_status, 'fulfilled')
        self.assertEqual(track.source_id, data['aliexpress_order_id'])
        self.assertEqual(track.source_type, data['source_type'])

        # Wrong source id
        r = self.client.post('/api/shopify/order-fulfill', {
            **data,
            'aliexpress_order_id': 'https://trade.aliexpress.com/order_detail.htm?orderId=123'
        })

        self.assertEqual(r.status_code, 501)
        self.assertIn('should not be a link', r.json().get('error'))

        # Prevent from Oberlo
        r = self.client.post('/api/shopify/order-fulfill', {**data, 'aliexpress_order_id': ''}, HTTP_REFERER='https://oberlo.com')

        self.assertEqual(r.status_code, 202)
        self.assertIn('Nothing to import', r.json().get('message'))

    @patch('shopified_core.permissions.can_add_product')
    def test_post_import_product(self, can_add_product_mock):
        product = f.ShopifyProductFactory(store=self.store, user=self.user, shopify_id=12345678)
        data = {
            'store': self.store.id,
            'product': product.shopify_id,
            'supplier': 'https://www.aliexpress.com/item/~/32961038442.html',
        }

        can_add_product_mock.return_value = [False, 1, 1]
        r = self.client.post('/api/shopify/import-product', data)
        self.assertEqual(r.status_code, 401)
        can_add_product_mock.return_value = [True, 1, 1]

        r = self.client.post('/api/shopify/import-product', data)
        product.refresh_from_db()
        self.assertTrue(product.have_supplier())

        r = self.client.post('/api/shopify/import-product', data)
        self.assertEqual(r.status_code, 489)
        self.assertIn('connected', r.json().get('error'))

    def test_post_order_fulfill_update(self):
        track = f.ShopifyOrderTrackFactory(user=self.user, store=self.store)
        data = {
            'store': self.store.id,
            'order': track.id,
            'source_id': '123',
            'tracking_number': '123',
            'status': 'PLACE_ORDER_SUCCESS',
            'end_reason': 'buyer_accept_goods'
        }

        r = self.client.post('/api/shopify/order-fulfill-update', data)
        self.assertEqual(r.status_code, 200)
        track.refresh_from_db()
        self.assertEqual(track.source_tracking, data['tracking_number'])
        self.assertEqual(self.store.shopifyorderlog_set.count(), 1)

        r = self.client.post('/api/shopify/order-fulfill-update', {**data, 'bundle': {'source_id': '123'}})
        self.assertEqual(r.status_code, 200)
        track.refresh_from_db()
        track_data = json.loads(track.data)
        self.assertEqual(track_data['bundle']['123']['source_status'], data['status'])
        self.assertEqual(track_data['bundle']['123']['source_tracking'], data['tracking_number'])

    def test_post_order_fulfill_update_email(self):
        track = f.ShopifyOrderTrackFactory(user=self.user, store=self.store)
        data = {
            'store': self.store.id,
            'order': track.id,
            'source_id': '123',
            'tracking_number': '123',
            'status': 'PLACE_ORDER_SUCCESS',
            'end_reason': 'buyer_accept_goods'
        }

        self.user.email = 'test@example.com'
        self.user.set_config('alert_order_cancelled', 'notify')
        self.user.save()
        self.client.post('/api/shopify/order-fulfill-update', data)
        self.assertEqual(len(mail.outbox), 0)

    def test_post_product_remove_board(self):
        self.user.profile.plan.permissions.add(f.AppPermissionFactory(name='edit_product_boards.sub', description=''))
        board = f.ShopifyBoardFactory(user=self.user)
        product = f.ShopifyProductFactory(store=self.store, user=self.user, shopify_id=12345678)
        board.products.add(product)
        data = {'products[]': [product.id], 'board': board.id}
        r = self.client.post('/api/shopify/product-remove-board', data)
        self.assertEqual(r.status_code, 200)
        count = board.products.count()
        self.assertEqual(count, 0)

    def test_post_board_delete(self):
        self.user.profile.plan.permissions.add(f.AppPermissionFactory(name='edit_product_boards.sub', description=''))
        board = f.ShopifyBoardFactory(user=self.user)
        data = {'board': board.id}
        r = self.client.post('/api/shopify/board-delete', data)
        self.assertEqual(r.status_code, 200)
        count = self.user.shopifyboard_set.count()
        self.assertEqual(count, 0)

    @patch('leadgalaxy.tasks.update_product_connection.delay')
    def test_post_product_delete(self, update_product_connection):
        self.user.profile.plan.permissions.add(f.AppPermissionFactory(name='delete_products.sub', description=''))
        product = f.ShopifyProductFactory(store=self.store, user=self.user, shopify_id=12345678)
        data = {'product': product.id}
        r = self.client.post('/api/shopify/product-delete', data)
        self.assertEqual(r.status_code, 200)
        count = self.user.shopifyproduct_set.count()
        self.assertEqual(count, 0)
        update_product_connection.assert_called_with(self.store.id, product.shopify_id)

    @patch('leadgalaxy.api.unmonitor_store')
    @patch('leadgalaxy.utils.detach_webhooks')
    @patch('requests.delete')
    def test_post_delete_store(self, mock_delete, detach_webhooks, unmonitor_store):
        self.store.version = 2
        self.store.save()
        data = {'store': self.store.id}
        r = self.client.post('/api/delete-store', data)
        self.assertEqual(r.status_code, 200)
        self.store.refresh_from_db()
        self.assertEqual(self.store.is_active, False)
        mock_delete.assert_called_once()
        unmonitor_store.assert_called_with(self.store)
        detach_webhooks.assert_called_with(self.store, delete_too=True)

    def test_delete_product_metadata(self):
        product = f.ShopifyProductFactory(store=self.store, user=self.user, source_id=12345678)
        supplier1 = f.ProductSupplierFactory(product=product)
        supplier2 = f.ProductSupplierFactory(product=product)
        product.default_supplier = supplier1
        product.save()
        params = '?product={}&export={}'.format(product.id, supplier1.id)
        r = self.client.delete('/api/shopify/product-metadata' + params)
        self.assertEqual(r.status_code, 200)
        count = product.productsupplier_set.count()
        self.assertEqual(count, 1)
        product.refresh_from_db()
        self.assertEqual(product.default_supplier, supplier2)

    @patch('leadgalaxy.tasks.sync_shopify_product_quantities.apply_async')
    @patch('leadgalaxy.utils.update_shopify_product_vendor')
    def test_post_product_metadata_default(self, update_shopify_product_vendor, sync_shopify_product_quantities):
        self.user.set_config('supplier_change_inventory_sync', True)
        self.user.set_config('update_product_vendor', True)
        product = f.ShopifyProductFactory(store=self.store, user=self.user, shopify_id=12345678)
        supplier = f.ProductSupplierFactory(product=product)
        data = {'product': product.id, 'export': supplier.id}
        r = self.client.post('/api/shopify/product-metadata-default', data)
        self.assertEqual(r.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.default_supplier, supplier)
        update_shopify_product_vendor.assert_called_with(product.store, product.shopify_id, product.default_supplier.supplier_name)
        sync_shopify_product_quantities.assert_called_with(args=[product.id])

    @patch('leadgalaxy.utils.update_shopify_product_vendor')
    def test_post_product_metadata(self, update_shopify_product_vendor):
        self.user.profile.plan.permissions.add(f.AppPermissionFactory(name='product_metadata.use', description=''))
        self.user.set_config('update_product_vendor', True)
        product = f.ShopifyProductFactory(store=self.store, user=self.user, shopify_id=12345678)
        data = {
            'product': product.id,
            'original-link': 'https://www.aliexpress.com/item/32213964945.html',
            'supplier-link': '123',
            'supplier-name': 'test'
        }
        r = self.client.post('/api/shopify/product-metadata', data)
        self.assertEqual(r.status_code, 200)
        product.refresh_from_db()
        count = product.productsupplier_set.count()
        self.assertEqual(count, 1)
        self.assertIsNotNone(product.default_supplier)
        update_shopify_product_vendor.assert_called_with(product.store, product.shopify_id, product.default_supplier.supplier_name)

    @patch('leadgalaxy.models.ShopifyStore.get_info', new_callable=PropertyMock)
    def test_get_store_verify(self, get_info):
        get_info.return_value = {'name': 'Test Shopify Store'}
        r = self.client.get('/api/store-verify', {'store': self.store.id})
        get_info.assert_called_once()
        self.assertEqual(r.status_code, 200)

    def test_post_alert_archive(self):
        product = f.ShopifyProductFactory(store=self.store, user=self.user, shopify_id=12345678)
        product_change1 = f.ProductChangeFactory(shopify_product=product, user=self.user)
        product_change2 = f.ProductChangeFactory(shopify_product=product, user=self.user)
        self.assertEqual(product_change1.hidden, False)
        self.assertEqual(product_change2.hidden, False)

        data = {
            'alert': product_change1.id,
        }
        r = self.client.post('/api/alert-archive', data)
        self.assertEqual(r.status_code, 200)
        product_change1.refresh_from_db()
        product_change2.refresh_from_db()
        self.assertEqual(product_change1.hidden, True)
        self.assertEqual(product_change2.hidden, False)

        data = {
            'store': self.store.id,
            'all': 1,
        }
        r = self.client.post('/api/alert-archive', data)
        self.assertEqual(r.status_code, 200)
        product_change2.refresh_from_db()
        self.assertEqual(product_change2.hidden, True)

    def test_post_alert_delete(self):
        product = f.ShopifyProductFactory(store=self.store, user=self.user, shopify_id=12345678)
        f.ProductChangeFactory(shopify_product=product, user=self.user)
        count = self.user.productchange_set.count()
        self.assertEqual(count, 1)

        data = {
            'store': self.store.id,
        }
        r = self.client.post('/api/alert-delete', data)
        self.assertEqual(r.status_code, 200)
        count = self.user.productchange_set.count()
        self.assertEqual(count, 0)


# Fix for last_seen cache
@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
class SyncAliexpressTestCase(BaseTestCase):
    def setUp(self):
        self.password = 'test'
        self.parent_user = f.UserFactory()
        self.parent_user.set_password(self.password)
        self.parent_user.save()

        self.subuser = f.UserFactory()
        self.subuser.profile.subuser_parent = self.parent_user
        self.subuser.profile.save()
        self.subuser.set_password(self.password)
        self.subuser.save()

        permission = f.AppPermissionFactory(name='orders.use')
        self.parent_user.profile.plan.permissions.add(permission)

        self.store = f.ShopifyStoreFactory(user=self.parent_user)
        self.subuser.profile.subuser_stores.add(self.store)

        created_at = timezone.now()
        for i in range(10):
            with patch('django.utils.timezone.now', Mock(return_value=created_at - timedelta(days=3 * i))):  # mock auto_now_add=True
                # Unfulfilled
                f.ShopifyOrderTrackFactory(user=self.parent_user,
                                           store=self.store)

                # Fulfilled
                f.ShopifyOrderTrackFactory(user=self.parent_user,
                                           store=self.store,
                                           source_id=uuid.uuid4().hex,
                                           source_tracking='1234567890',
                                           shopify_status='fulfilled',
                                           source_status='FINISH')

    @patch('leadgalaxy.utils.get_tracking_orders')
    def user_login(self, user, get_tracking_orders):
        get_tracking_orders.return_value = []
        logged_in = self.client.login(username=user.username, password=self.password)

        LastSeen.objects.seen(user=user.models_user, module='website')

        return logged_in

    def get_request(self, url, data, response_status=200):
        r = self.client.get(url, data, content_type='application/json')
        self.assertEqual(r.status_code, response_status)

        return r

    def test_orders_access_permission(self):
        data = {'store': self.store.pk}

        self.user_login(self.parent_user)
        response = self.get_request('/api/order-fulfill', data)
        self.assertNotEqual(response.status_code, 402)

        self.client.logout()

        self.user_login(self.subuser)
        response = self.get_request('/api/order-fulfill', data)
        self.assertNotEqual(response.status_code, 402)

    def test_subuser_order_unfulfilled_only_count(self):
        self.user_login(self.subuser)

        data = {
            'store': self.store.pk,
            'all': 'true',
            'unfulfilled_only': 'true',
            'created_at': '',
            'count_only': 'true'
        }

        response = self.get_request('/api/order-fulfill', data)
        json_response = json.loads(response.content)
        self.assertEqual(json_response['pending'], 10)

    def test_order_all_only_count(self):
        self.user_login(self.parent_user)

        data = {
            'store': self.store.pk,
            'all': 'true',
            'unfulfilled_only': 'false',
            'created_at': '',
            'count_only': 'true'
        }

        response = self.get_request('/api/order-fulfill', data)
        json_response = json.loads(response.content)
        self.assertEqual(json_response['pending'], 20)

    def test_last_week_orders_only(self):
        self.user_login(self.parent_user)

        created_at = '{}-{}'.format(
            (timezone.now() - timedelta(days=7)).strftime('%m/%d/%Y'),
            timezone.now().strftime('%m/%d/%Y')
        )

        data = {
            'store': self.store.pk,
            'all': 'false',
            'unfulfilled_only': 'false',
            'created_at': created_at,
            'count_only': 'true',
        }

        response = self.get_request('/api/order-fulfill', data)
        json_response = json.loads(response.content)
        self.assertEqual(json_response['pending'], 6)

    def test_unfulfilled_only(self):
        self.user_login(self.parent_user)

        created_at = '{}-{}'.format(
            (timezone.now() - timedelta(days=7)).strftime('%m/%d/%Y'),
            timezone.now().strftime('%m/%d/%Y')
        )
        data = {
            'store': self.store.pk,
            'all': 'false',
            'unfulfilled_only': 'true',
            'created_at': created_at,
            'count_only': 'false',
        }

        response = self.get_request('/api/order-fulfill', data)
        orders = json.loads(response.content)

        for order in orders:
            self.assertEqual(order['source_id'], '')
