import arrow

from mock import patch, Mock

from django.test import TestCase
from django.utils import timezone

from ..utils import sync_products, sync_collections
from ..models import CommerceHQProduct, CommerceHQCollection
from .factories import (
    CommerceHQStoreFactory,
    CommerceHQProductFactory,
    CommerceHQCollectionFactory,
)


class SyncProductsTestCase(TestCase):
    def setUp(self):
        self.product_data1 = {
            'id': 1,
            'title': 'Test',
            'type': 'Test Product',
            'seo_title': 'Test SEO Title',
            'created_at': arrow.get(timezone.now()).timestamp,
            'update_at': arrow.get(timezone.now()).timestamp,
        }

    @patch('commercehq_core.utils.fetch_resource')
    def test_must_add_new_products(self, fetch_resource):
        response = Mock()
        items = [self.product_data1]
        response.json = Mock(return_value={'items': items})
        fetch_resource.return_value = response

        store = CommerceHQStoreFactory()
        sync_products(store)
        count = CommerceHQProduct.objects.filter(product_id=self.product_data1['id'],
                                                 store=store).count()
        self.assertEquals(count, 1)
        self.assertEquals(fetch_resource.call_count, 1)

    @patch('commercehq_core.utils.fetch_resource')
    def test_must_update_old_products(self, fetch_resource):
        store = CommerceHQStoreFactory()
        product = CommerceHQProductFactory(store=store)
        response = Mock()
        self.product_data1['id'] = product.product_id
        self.product_data1['title'] = 'Changed'
        items = [self.product_data1]
        response.json = Mock(return_value={'items': items})
        fetch_resource.return_value = response
        sync_products(product.store)
        product.refresh_from_db()
        self.assertEquals(product.title, self.product_data1['title'])
        self.assertEquals(CommerceHQProduct.objects.count(), 1)


class SyncCollectionsTestCase(TestCase):
    def setUp(self):
        self.collection_data1 = {
            'id': 1,
            'title': 'Test Collection',
            'is_auto': False
        }

    @patch('commercehq_core.utils.fetch_resource')
    def test_must_add_new_collection(self, fetch_resource):
        response = Mock()
        collections = [self.collection_data1]
        response.json = Mock(return_value=collections)
        fetch_resource.return_value = response

        store = CommerceHQStoreFactory()
        sync_collections(store)

        count = CommerceHQCollection.objects.filter(
            collection_id=self.collection_data1['id'], store=store
        ).count()

        self.assertEquals(count, 1)
        self.assertEquals(fetch_resource.call_count, 1)

    @patch('commercehq_core.utils.fetch_resource')
    def test_must_update_old_collections(self, fetch_resource):
        store = CommerceHQStoreFactory()
        collection = CommerceHQCollectionFactory(store=store)
        response = Mock()
        self.collection_data1['id'] = collection.collection_id
        self.collection_data1['title'] = 'Changed'
        collections = [self.collection_data1]
        response.json = Mock(return_value=collections)
        fetch_resource.return_value = response
        sync_collections(collection.store)
        collection.refresh_from_db()
        self.assertEquals(collection.title, self.collection_data1['title'])
        self.assertEquals(CommerceHQCollection.objects.count(), 1)

