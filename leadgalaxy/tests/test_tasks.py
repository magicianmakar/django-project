import json
from unittest.mock import patch

from lib.test import BaseTestCase
from leadgalaxy.tests.factories import (
    ShopifyProductFactory,
    ShopifyStoreFactory,
    UserFactory,
)

from leadgalaxy.tasks import (
    link_variants_to_new_images,
)


class TasksTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory()
        password = 'test'
        self.user.set_password(password)
        self.user.save()

        self.product = ShopifyProductFactory(user=self.user)
        self.store = ShopifyStoreFactory(user=self.user)

    def test_link_variants_to_new_images(self):
        product = self.product

        new_src = 'http://example.com/new'
        new_src_2 = 'http://example.com/new2'
        old_src = 'http://example.com/old'
        old_src_2 = 'http://example.com/old2'

        new_data = dict(
            product=dict(
                images=[{
                    'src': new_src,
                }],
            )
        )

        old_to_new_image_url = json.dumps({
            old_src: new_src,
            old_src_2: new_src_2,
        })

        req_data = {'old_to_new_url': old_to_new_image_url}

        mock_product = dict(
            images=[{
                'src': old_src,
                'variant_ids': [1, 2],
            }, {
                'src': 'non-existing',
            }, {
                'src': old_src_2,
            }],
        )

        with patch('leadgalaxy.tasks.utils.get_shopify_product',
                   return_value=mock_product):
            updated_new_data = link_variants_to_new_images(product,
                                                           new_data,
                                                           req_data)

        new_images = updated_new_data['product']['images']
        self.assertEqual(new_images[0]['src'], new_src)
        self.assertEqual(new_images[0]['variant_ids'], [1, 2])
