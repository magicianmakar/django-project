import json

from django.test import TestCase
from leadgalaxy.tests.factories import (
    UserFactory,
    AppPermissionFactory
)


class BaseTestCase(TestCase):
    maxDiff = None

    def assertEqualCaseInsensitive(self, expected, actual):
        expected_lower = expected.lower()
        actual_lower = actual.lower()
        if expected_lower != actual_lower:
            self.fail('str did not match:\n+{!r}\n-{!r}\n\nComparing:\n+{!r}\n-{!r}'.format(
                expected,
                actual,
                expected_lower,
                actual_lower))


class ProductAlertsBase(BaseTestCase):
    store_factory = None
    product_factory = None
    supplier_factory = None
    change_factory = None

    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.store = self.store_factory(user=self.user)

        product = self.product = self.product_factory(
            user=self.user,
            store=self.store,
            source_id=12345678,
        )

        supplier = self.supplier_factory(product=product)
        supplier.product_url = 'http://www.aliexpress.com/123'
        supplier.save()

        product.default_supplier = supplier
        product.save()

        self.subuser = UserFactory()
        self.subuser_password = 'test'
        self.subuser.set_password(self.subuser_password)
        self.subuser.save()
        self.subuser.profile.subuser_parent = self.user
        self.subuser.profile.save()

        permission = AppPermissionFactory(name='price_changes.use')
        self.subuser.profile.plan.permissions.add(permission)
        self.subuser.profile.save()

        self.change_data1 = json.dumps([
            {'name': 'offline', 'level': 'product'},
        ])

        self.change_data2 = json.dumps([
            {'name': 'offline', 'level': 'product'},
        ])
