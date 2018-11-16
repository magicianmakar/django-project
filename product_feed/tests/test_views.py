from mock import patch, Mock

from lib.test import BaseTestCase
from django.urls import reverse

from leadgalaxy.tests.factories import (
    UserFactory,
    GroupPlanFactory,
    ShopifyStoreFactory,
    AppPermissionFactory
)

from commercehq_core.tests.factories import CommerceHQStoreFactory
from woocommerce_core.tests.factories import WooStoreFactory
from gearbubble_core.tests.factories import GearBubbleStoreFactory

from ..models import FeedStatus, CommerceHQFeedStatus, WooFeedStatus, GearBubbleFeedStatus
from .factories import (
    FeedStatusFactory,
    CommerceHQFeedStatusFactory,
    WooFeedStatusFactory,
    GearBubbleFeedStatusFactory,
)


class ProductFeeds(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.user.profile.plan = GroupPlanFactory()
        self.user.profile.save()

        self.permission = AppPermissionFactory(name='product_feeds.use')
        self.user.profile.plan.permissions.add(self.permission)

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    def test_must_be_logged_in_for_shopify_store_feeds(self):
        path = '/marketing/feeds'
        r = self.client.get(path)
        self.assertRedirects(r, '%s?next=%s' % (reverse('login'), path))

    def test_must_be_logged_in_for_chq_store_feeds(self):
        path = '/marketing/feeds/chq'
        r = self.client.get(path)
        self.assertRedirects(r, '%s?next=%s' % (reverse('login'), path))

    def test_must_be_logged_in_for_woo_store_feeds(self):
        path = '/marketing/feeds/woo'
        r = self.client.get(path)
        self.assertRedirects(r, '%s?next=%s' % (reverse('login'), path))

    def test_must_be_logged_in_for_gear_store_feeds(self):
        path = '/marketing/feeds/gear'
        r = self.client.get(path)
        self.assertRedirects(r, '%s?next=%s' % (reverse('login'), path))

    def test_must_use_shopify_product_feeds_template(self):
        self.login()
        r = self.client.get('/marketing/feeds')
        self.assertTemplateUsed(r, 'product_feeds.html')

    def test_must_use_chq_product_feeds_template(self):
        self.login()
        r = self.client.get('/marketing/feeds/chq')
        self.assertTemplateUsed(r, 'chq_product_feeds.html')

    def test_must_use_woo_product_feeds_template(self):
        self.login()
        r = self.client.get('/marketing/feeds/woo')
        self.assertTemplateUsed(r, 'woo_product_feeds.html')

    def test_must_use_gear_product_feeds_template(self):
        self.login()
        r = self.client.get('/marketing/feeds/gear')
        self.assertTemplateUsed(r, 'gear_product_feeds.html')

    def test_must_set_all_variants_of_shopify_store(self):
        self.login()
        store = ShopifyStoreFactory(user=self.user)
        feed = FeedStatusFactory(store=store)
        data = {'feed': feed.id, 'all_variants': False}
        r = self.client.post('/marketing/feeds', data)
        feed.refresh_from_db()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(feed.all_variants)

    def test_must_set_all_variants_of_chq_store(self):
        self.login()
        store = CommerceHQStoreFactory(user=self.user)
        feed = CommerceHQFeedStatusFactory(store=store)
        data = {'feed': feed.id, 'all_variants': False}
        r = self.client.post('/marketing/feeds/chq', data)
        feed.refresh_from_db()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(feed.all_variants)

    def test_must_set_all_variants_of_woo_store(self):
        self.login()
        store = WooStoreFactory(user=self.user)
        feed = WooFeedStatusFactory(store=store)
        data = {'feed': feed.id, 'all_variants': False}
        r = self.client.post('/marketing/feeds/woo', data)
        feed.refresh_from_db()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(feed.all_variants)

    def test_must_set_all_variants_of_gear_store(self):
        self.login()
        store = GearBubbleStoreFactory(user=self.user)
        feed = GearBubbleFeedStatusFactory(store=store)
        data = {'feed': feed.id, 'all_variants': False}
        r = self.client.post('/marketing/feeds/gear', data)
        feed.refresh_from_db()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(feed.all_variants)

    def test_must_set_include_variants_id_of_shopify_store(self):
        self.login()
        store = ShopifyStoreFactory(user=self.user)
        feed = FeedStatusFactory(store=store)
        data = {'feed': feed.id, 'include_variants_id': False}
        r = self.client.post('/marketing/feeds', data)
        feed.refresh_from_db()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(feed.include_variants_id)

    def test_must_set_include_variants_id_of_chq_store(self):
        self.login()
        store = CommerceHQStoreFactory(user=self.user)
        feed = CommerceHQFeedStatusFactory(store=store)
        data = {'feed': feed.id, 'include_variants_id': False}
        r = self.client.post('/marketing/feeds/chq', data)
        feed.refresh_from_db()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(feed.include_variants_id)

    def test_must_set_include_variants_id_of_woo_store(self):
        self.login()
        store = WooStoreFactory(user=self.user)
        feed = WooFeedStatusFactory(store=store)
        data = {'feed': feed.id, 'include_variants_id': False}
        r = self.client.post('/marketing/feeds/woo', data)
        feed.refresh_from_db()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(feed.include_variants_id)

    def test_must_set_include_variants_id_of_gear_store(self):
        self.login()
        store = GearBubbleStoreFactory(user=self.user)
        feed = GearBubbleFeedStatusFactory(store=store)
        data = {'feed': feed.id, 'include_variants_id': False}
        r = self.client.post('/marketing/feeds/gear', data)
        feed.refresh_from_db()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(feed.include_variants_id)

    @patch('leadgalaxy.tasks.generate_feed.delay')
    def test_must_update_feed_of_shopify_store(self, generate_feed):
        generate_feed.return_value = None
        self.login()
        store = ShopifyStoreFactory(user=self.user)
        feed = FeedStatusFactory(store=store)
        data = {'feed': feed.id, 'update_feed': True}
        r = self.client.post('/marketing/feeds', data)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(generate_feed.called)

    @patch('leadgalaxy.tasks.generate_chq_feed.delay')
    def test_must_update_feed_of_chq_store(self, generate_chq_feed):
        generate_chq_feed.return_value = None
        self.login()
        store = CommerceHQStoreFactory(user=self.user)
        feed = CommerceHQFeedStatusFactory(store=store)
        data = {'feed': feed.id, 'update_feed': True}
        r = self.client.post('/marketing/feeds/chq', data)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(generate_chq_feed.called)

    @patch('leadgalaxy.tasks.generate_woo_feed.delay')
    def test_must_update_feed_of_woo_store(self, generate_woo_feed):
        generate_woo_feed.return_value = None
        self.login()
        store = WooStoreFactory(user=self.user)
        feed = WooFeedStatusFactory(store=store)
        data = {'feed': feed.id, 'update_feed': True}
        r = self.client.post('/marketing/feeds/woo', data)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(generate_woo_feed.called)

    @patch('leadgalaxy.tasks.generate_gear_feed.delay')
    def test_must_update_feed_of_gear_store(self, generate_gear_feed):
        generate_gear_feed.return_value = None
        self.login()
        store = GearBubbleStoreFactory(user=self.user)
        feed = GearBubbleFeedStatusFactory(store=store)
        data = {'feed': feed.id, 'update_feed': True}
        r = self.client.post('/marketing/feeds/gear', data)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(generate_gear_feed.called)

    def test_must_return_error_of_missing_parameters_for_shopify_store(self):
        self.login()
        store = ShopifyStoreFactory(user=self.user)
        feed = FeedStatusFactory(store=store)
        data = {'feed': feed.id}
        r = self.client.post('/marketing/feeds', data)
        self.assertEqual(r.status_code, 500)
        self.assertIn('Missing parameters', r.content)

    def test_must_return_error_of_missing_parameters_for_chq_store(self):
        self.login()
        store = CommerceHQStoreFactory(user=self.user)
        feed = CommerceHQFeedStatusFactory(store=store)
        data = {'feed': feed.id}
        r = self.client.post('/marketing/feeds/chq', data)
        self.assertEqual(r.status_code, 500)
        self.assertIn('Missing parameters', r.content)

    def test_must_return_error_of_missing_parameters_for_woo_store(self):
        self.login()
        store = WooStoreFactory(user=self.user)
        feed = WooFeedStatusFactory(store=store)
        data = {'feed': feed.id}
        r = self.client.post('/marketing/feeds/woo', data)
        self.assertEqual(r.status_code, 500)
        self.assertIn('Missing parameters', r.content)

    def test_must_return_error_of_missing_parameters_for_gear_store(self):
        self.login()
        store = GearBubbleStoreFactory(user=self.user)
        feed = GearBubbleFeedStatusFactory(store=store)
        data = {'feed': feed.id}
        r = self.client.post('/marketing/feeds/gear', data)
        self.assertEqual(r.status_code, 500)
        self.assertIn('Missing parameters', r.content)

    def test_must_return_feed_for_shopify_store(self):
        self.login()
        store = ShopifyStoreFactory(user=self.user)
        feed = FeedStatusFactory(store=store)
        r = self.client.get('/marketing/feeds')
        feeds = FeedStatus.objects.filter(store__user=self.user)
        self.assertItemsEqual(feeds, r.context['feeds'])

    def test_must_return_feed_for_chq_store(self):
        self.login()
        store = CommerceHQStoreFactory(user=self.user)
        feed = CommerceHQFeedStatusFactory(store=store)
        r = self.client.get('/marketing/feeds/chq')
        feeds = CommerceHQFeedStatus.objects.filter(store__user=self.user)
        self.assertItemsEqual(feeds, r.context['feeds'])

    def test_must_return_feed_for_woo_store(self):
        self.login()
        store = WooStoreFactory(user=self.user)
        feed = WooFeedStatusFactory(store=store)
        r = self.client.get('/marketing/feeds/woo')
        feeds = WooFeedStatus.objects.filter(store__user=self.user)
        self.assertItemsEqual(feeds, r.context['feeds'])

    def test_must_return_feed_for_gear_store(self):
        self.login()
        store = GearBubbleStoreFactory(user=self.user)
        feed = GearBubbleFeedStatusFactory(store=store)
        r = self.client.get('/marketing/feeds/gear')
        feeds = GearBubbleFeedStatus.objects.filter(store__user=self.user)
        self.assertItemsEqual(feeds, r.context['feeds'])

    def test_must_show_upgrade_page_for_shopify_store(self):
        self.login()
        self.user.profile.plan.permissions.remove(self.permission)
        r = self.client.get('/marketing/feeds')
        self.assertTemplateUsed('upgrade.html')

    def test_must_show_upgrade_page_for_chq_store(self):
        self.login()
        self.user.profile.plan.permissions.remove(self.permission)
        r = self.client.get('/marketing/feeds/chq')
        self.assertTemplateUsed('commercehq/upgrade.html')

    def test_must_show_upgrade_page_for_woo_store(self):
        self.login()
        self.user.profile.plan.permissions.remove(self.permission)
        r = self.client.get('/marketing/feeds/woo')
        self.assertTemplateUsed('woocommerce/upgrade.html')

    def test_must_show_upgrade_page_for_gear_store(self):
        self.login()
        self.user.profile.plan.permissions.remove(self.permission)
        r = self.client.get('/marketing/feeds/gear')
        self.assertTemplateUsed('gearbubble/upgrade.html')


class GetProductFeed(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.user.profile.plan = GroupPlanFactory()
        self.user.profile.save()

        self.permission = AppPermissionFactory(name='product_feeds.use')
        self.user.profile.plan.permissions.add(self.permission)

    def login(self):
        self.client.login(username=self.user.username, password=self.password)

    @patch('product_feed.models.ShopifyStore.get_info', Mock(return_value=True))
    @patch('product_feed.views.generate_product_feed')
    def test_must_generate_shopify_product_feed(self, generate_product_feed):
        generate_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = ShopifyStoreFactory(user=self.user)
        r = self.client.get('/marketing/feeds/{}'.format(store.store_hash[:8]))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(generate_product_feed.called)

    @patch('product_feed.views.generate_chq_product_feed')
    def test_must_generate_chq_product_feed(self, generate_chq_product_feed):
        generate_chq_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = CommerceHQStoreFactory(user=self.user)
        r = self.client.get('/marketing/feeds/chq/{}'.format(store.store_hash[:8]))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(generate_chq_product_feed.called)

    @patch('product_feed.views.generate_woo_product_feed')
    def test_must_generate_woo_product_feed(self, generate_woo_product_feed):
        generate_woo_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = WooStoreFactory(user=self.user)
        r = self.client.get('/marketing/feeds/woo/{}'.format(store.store_hash[:8]))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(generate_woo_product_feed.called)

    @patch('product_feed.views.generate_gear_product_feed')
    def test_must_generate_gear_product_feed(self, generate_gear_product_feed):
        generate_gear_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = GearBubbleStoreFactory(user=self.user)
        r = self.client.get('/marketing/feeds/gear/{}'.format(store.store_hash[:8]))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(generate_gear_product_feed.called)

    def test_must_have_permissions_to_generate_shopify_feed(self):
        self.login()
        self.user.profile.plan.permissions.remove(self.permission)
        store = ShopifyStoreFactory(user=self.user)
        r = self.client.get('/marketing/feeds/{}'.format(store.store_hash[:8]))
        self.assertEqual(r.status_code, 404)

    def test_must_have_permissions_to_generate_chq_feed(self):
        self.login()
        self.user.profile.plan.permissions.remove(self.permission)
        store = CommerceHQStoreFactory(user=self.user)
        r = self.client.get('/marketing/feeds/chq/{}'.format(store.store_hash[:8]))
        self.assertEqual(r.status_code, 404)

    def test_must_have_permissions_to_generate_woo_feed(self):
        self.login()
        self.user.profile.plan.permissions.remove(self.permission)
        store = WooStoreFactory(user=self.user)
        r = self.client.get('/marketing/feeds/woo/{}'.format(store.store_hash[:8]))
        self.assertEqual(r.status_code, 404)

    def test_must_have_permissions_to_generate_gear_feed(self):
        self.login()
        self.user.profile.plan.permissions.remove(self.permission)
        store = GearBubbleStoreFactory(user=self.user)
        r = self.client.get('/marketing/feeds/gear/{}'.format(store.store_hash[:8]))
        self.assertEqual(r.status_code, 404)

    @patch('product_feed.models.ShopifyStore.get_info', Mock(return_value=True))
    @patch('product_feed.views.generate_product_feed')
    def test_must_change_revision_for_shopify_product_feed(self, generate_product_feed):
        generate_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = ShopifyStoreFactory(user=self.user)
        path = '/marketing/feeds/{}'.format(store.store_hash[:8])
        r = self.client.get(path + '/9')
        store.feedstatus.refresh_from_db()
        self.assertEqual(store.feedstatus.revision, 9)

    @patch('product_feed.views.generate_chq_product_feed')
    def test_must_change_revision_for_chq_product_feed(self, generate_chq_product_feed):
        generate_chq_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = CommerceHQStoreFactory(user=self.user)
        path = '/marketing/feeds/chq/{}'.format(store.store_hash[:8])
        r = self.client.get(path + '/9')
        store.feedstatus.refresh_from_db()
        self.assertEqual(store.feedstatus.revision, 9)

    @patch('product_feed.views.generate_woo_product_feed')
    def test_must_change_revision_for_woo_product_feed(self, generate_woo_product_feed):
        generate_woo_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = WooStoreFactory(user=self.user)
        path = '/marketing/feeds/woo/{}'.format(store.store_hash[:8])
        r = self.client.get(path + '/9')
        store.feedstatus.refresh_from_db()
        self.assertEqual(store.feedstatus.revision, 9)

    @patch('product_feed.views.generate_gear_product_feed')
    def test_must_change_revision_for_gear_product_feed(self, generate_gear_product_feed):
        generate_gear_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = GearBubbleStoreFactory(user=self.user)
        path = '/marketing/feeds/gear/{}'.format(store.store_hash[:8])
        r = self.client.get(path + '/9')
        store.feedstatus.refresh_from_db()
        self.assertEqual(store.feedstatus.revision, 9)

    @patch('product_feed.models.ShopifyStore.get_info', Mock(return_value=True))
    @patch('product_feed.views.generate_product_feed')
    def test_must_update_fb_access_date_for_shopify_product_feed(self, generate_product_feed):
        generate_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = ShopifyStoreFactory(user=self.user)
        feed = FeedStatusFactory(fb_access_at=None, store=store)
        headers = {'HTTP_USER_AGENT': 'facebookexternalhit'}
        r = self.client.get('/marketing/feeds/{}'.format(store.store_hash[:8]), **headers)
        feed.refresh_from_db()
        self.assertIsNotNone(feed.fb_access_at)

    @patch('product_feed.views.generate_chq_product_feed')
    def test_must_update_fb_access_date_for_chq_product_feed(self, generate_chq_product_feed):
        generate_chq_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = CommerceHQStoreFactory(user=self.user)
        feed = CommerceHQFeedStatusFactory(fb_access_at=None, store=store)
        headers = {'HTTP_USER_AGENT': 'facebookexternalhit'}
        r = self.client.get('/marketing/feeds/chq/{}'.format(store.store_hash[:8]), **headers)
        feed.refresh_from_db()
        self.assertIsNotNone(feed.fb_access_at)

    @patch('product_feed.views.generate_woo_product_feed')
    def test_must_update_fb_access_date_for_woo_product_feed(self, generate_woo_product_feed):
        generate_woo_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = WooStoreFactory(user=self.user)
        feed = WooFeedStatusFactory(fb_access_at=None, store=store)
        headers = {'HTTP_USER_AGENT': 'facebookexternalhit'}
        r = self.client.get('/marketing/feeds/woo/{}'.format(store.store_hash[:8]), **headers)
        feed.refresh_from_db()
        self.assertIsNotNone(feed.fb_access_at)

    @patch('product_feed.views.generate_gear_product_feed')
    def test_must_update_fb_access_date_for_gear_product_feed(self, generate_gear_product_feed):
        generate_gear_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = GearBubbleStoreFactory(user=self.user)
        feed = GearBubbleFeedStatusFactory(fb_access_at=None, store=store)
        headers = {'HTTP_USER_AGENT': 'facebookexternalhit'}
        r = self.client.get('/marketing/feeds/gear/{}'.format(store.store_hash[:8]), **headers)
        feed.refresh_from_db()
        self.assertIsNotNone(feed.fb_access_at)

    @patch('product_feed.models.ShopifyStore.get_info', Mock(return_value=True))
    @patch('product_feed.views.generate_product_feed')
    def test_must_able_to_generate_feed_nocache_for_shopify_product_feed(self, generate_product_feed):
        generate_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = ShopifyStoreFactory(user=self.user)
        path = '/marketing/feeds/{}'.format(store.store_hash[:8]) + '?nocache=1'
        r = self.client.get(path)
        generate_product_feed.assert_called_with(store.feedstatus, nocache=True)

    @patch('product_feed.views.generate_chq_product_feed')
    def test_must_able_to_generate_feed_nocache_for_chq_product_feed(self, generate_chq_product_feed):
        generate_chq_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = CommerceHQStoreFactory(user=self.user)
        path = '/marketing/feeds/chq/{}'.format(store.store_hash[:8]) + '?nocache=1'
        r = self.client.get(path)
        generate_chq_product_feed.assert_called_with(store.feedstatus, nocache=True)

    @patch('product_feed.views.generate_woo_product_feed')
    def test_must_able_to_generate_feed_nocache_for_woo_product_feed(self, generate_woo_product_feed):
        generate_woo_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = WooStoreFactory(user=self.user)
        path = '/marketing/feeds/woo/{}'.format(store.store_hash[:8]) + '?nocache=1'
        r = self.client.get(path)
        generate_woo_product_feed.assert_called_with(store.feedstatus, nocache=True)

    @patch('product_feed.views.generate_gear_product_feed')
    def test_must_able_to_generate_feed_nocache_for_gear_product_feed(self, generate_gear_product_feed):
        generate_gear_product_feed.return_value = 'https://test-url.com'
        self.login()
        store = GearBubbleStoreFactory(user=self.user)
        path = '/marketing/feeds/gear/{}'.format(store.store_hash[:8]) + '?nocache=1'
        r = self.client.get(path)
        generate_gear_product_feed.assert_called_with(store.feedstatus, nocache=True)
