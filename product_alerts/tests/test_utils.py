from lib.test import BaseTestCase

from ..utils import (
    aliexpress_variants,
)


class UtilTestCase(BaseTestCase):
    def setUp(self):
        self.product_id = 32825336375

    def test_aliexpress_variants(self):
        variants = aliexpress_variants(self.product_id)
        self.assertEqual(len(variants), 8)
