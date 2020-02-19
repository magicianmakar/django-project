from unittest.mock import patch

from django.urls import reverse

from lib.test import BaseTestCase

from leadgalaxy.tests.factories import UserFactory

from ..tasks import product_export
from .factories import GrooveKartStoreFactory, GrooveKartProductFactory


class ProductExportTestCase(BaseTestCase):
    @patch('groovekart_core.models.GrooveKartStore.pusher_trigger')
    def test_must_not_export_already_connected_product(self, pusher_trigger):
        user = UserFactory()
        store = GrooveKartStoreFactory(user=user)
        product = GrooveKartProductFactory(store=store, source_id=1)
        product_url = reverse('gkart:product_detail', kwargs={'pk': product.id})
        pusher_data = {'success': False, 'product': product.id, 'product_url': product_url}
        pusher_data['error'] = 'Product already connected to GrooveKart store.'
        product_export(store.id, product.id, user.id)
        pusher_trigger.assert_called_with('product-export', pusher_data)
