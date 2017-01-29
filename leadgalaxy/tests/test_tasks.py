from mock import patch, Mock

from django.test import TestCase

from leadgalaxy.tasks import mark_as_ordered_note_attributes

from .factories import ShopifyStoreFactory


class MarkAsOrderedNoteAttributesTestCase(TestCase):
    @patch('leadgalaxy.utils.set_shopify_order_note_attributes')
    @patch('leadgalaxy.utils.get_shopify_order_note_attributes')
    def test_must_add_note_attributes(self, get_shopify_order_note_attributes, set_shopify_order_note_attributes):
        return_value = [{'name': 'foo', 'value': 'bar'}]
        get_shopify_order_note_attributes.return_value = return_value
        store = ShopifyStoreFactory()
        source_id = 1234567890
        mark_as_ordered_note_attributes(store.id, 1, source_id)

        name = 'Aliexpress Order #' + str(source_id)
        url = 'http://trade.aliexpress.com/order_detail.htm?orderId={0}'.format(source_id)
        aliexpress_order = {'name': name, 'value': url}

        return_value.append(aliexpress_order)

        set_shopify_order_note_attributes.assert_called_with(store, 1, return_value)

