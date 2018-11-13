import json

from mock import patch

from lib.test import BaseTestCase
from django.http import JsonResponse

from leadgalaxy.tests.factories import UserFactory
from gearbubble_core.tests.factories import GearBubbleStoreFactory, GearBubbleOrderTrackFactory


class GetAllStoresTest(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

    def login(self):
        return self.client.login(username=self.user.username, password=self.password)

    def test_must_include_gearbubble_stores(self):
        store = GearBubbleStoreFactory(user=self.user, title='test store')
        self.login()
        r = self.client.get('/api/all-stores')
        data = json.loads(r.content)
        store_data = data.pop()
        self.assertEqual(store_data['id'], store.pk)
        self.assertEqual(store_data['name'], store.title)
        self.assertEqual(store_data['type'], 'gear')
        self.assertEqual(store_data['url'], store.get_admin_url())


class PostQuickSaveTest(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

    def login(self):
        return self.client.login(username=self.user.username, password=self.password)

    @patch('gearbubble_core.api.GearBubbleApi.post_save_for_later')
    def test_must_call_gearbubble_post_save_for_later(self, post_save_for_later):
        post_save_for_later.return_value = JsonResponse({'status': 'ok'}, status=200)
        GearBubbleStoreFactory(user=self.user)
        self.user.is_superuser = True
        self.user.save()
        self.login()
        self.client.post('/api/quick-save', json.dumps({}), content_type='application/json')
        self.assertTrue(post_save_for_later.called)


class GetAllOrdersSyncTest(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

    def login(self):
        return self.client.login(username=self.user.username, password=self.password)

    def test_must_include_gearbubble_order_tracks(self):
        store = GearBubbleStoreFactory(user=self.user)
        track = GearBubbleOrderTrackFactory(user=self.user, store=store)
        self.user.is_superuser = True
        self.user.save()
        self.login()
        r = self.client.get('/api/all-orders-sync')
        orders = json.loads(r.content)['orders']
        order = orders.pop()
        self.assertEqual(order['store_type'], 'gear')
        self.assertEqual(order['order_id'], track.order_id)
        self.assertEqual(order['line_id'], track.line_id)
