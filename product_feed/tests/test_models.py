from mock import patch

from lib.test import BaseTestCase

from gearbubble_core.tests.factories import GearBubbleStoreFactory

from ..feed import GearBubbleProductFeed


class GearBubbleProductFeedTestCase(BaseTestCase):
    @patch('gearbubble_core.models.GearBubbleStore.get_gearbubble_products')
    def test_must_call_get_gearbubble_products(self, get_gearbubble_products):
        get_gearbubble_products.return_value = []
        store = GearBubbleStoreFactory()
        feed = GearBubbleProductFeed(store)
        feed.generate_feed()
        self.assertTrue(get_gearbubble_products.called)
