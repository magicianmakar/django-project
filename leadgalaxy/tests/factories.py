import datetime

from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify

import factory
import factory.fuzzy

NOW = timezone.now()
TOMORROW = NOW + datetime.timedelta(days=1)


class UserFactory(factory.django.DjangoModelFactory):
    id = factory.fuzzy.FuzzyInteger(999)
    username = factory.fuzzy.FuzzyText()
    first_name = factory.fuzzy.FuzzyText()
    last_name = factory.fuzzy.FuzzyText()
    is_active = True

    class Meta:
        model = User
        django_get_or_create = ['id']


class UserProfileFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    subuser_parent = None
    stores = factory.fuzzy.FuzzyInteger(999)
    products = factory.fuzzy.FuzzyInteger(999)
    boards = factory.fuzzy.FuzzyInteger(999)
    sub_users_limit = factory.fuzzy.FuzzyInteger(999)

    class Meta:
        model = 'leadgalaxy.UserProfile'


class ShopifyProductFactory(factory.django.DjangoModelFactory):
    id = factory.fuzzy.FuzzyInteger(9999)
    store = factory.SubFactory('leadgalaxy.tests.factories.ShopifyStoreFactory')
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    data = '{}'
    price = factory.fuzzy.FuzzyFloat(100.0)
    monitor_id = factory.fuzzy.FuzzyInteger(999)
    created_at = factory.fuzzy.FuzzyDateTime(NOW, TOMORROW)
    updated_at = factory.fuzzy.FuzzyDateTime(NOW, TOMORROW)

    class Meta:
        model = 'leadgalaxy.ShopifyProduct'
        django_get_or_create = ['id']


class ProductSupplierFactory(factory.django.DjangoModelFactory):
    product = factory.SubFactory('leadgalaxy.tests.factories.ShopifyProduct')

    class Meta:
        model = 'leadgalaxy.ProductSupplier'


class ShopifyStoreFactory(factory.django.DjangoModelFactory):
    title = factory.fuzzy.FuzzyText()
    api_url = factory.fuzzy.FuzzyText(prefix='https://:123456789abcdef@', suffix='.myshopify.com')
    shop = factory.fuzzy.FuzzyText()
    access_token = factory.fuzzy.FuzzyText()
    scope = factory.fuzzy.FuzzyText()
    is_active = True
    version = factory.fuzzy.FuzzyChoice((1, 2))
    list_index = factory.fuzzy.FuzzyInteger(999)
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    created_at = factory.fuzzy.FuzzyDateTime(NOW, TOMORROW)
    updated_at = factory.fuzzy.FuzzyDateTime(NOW, TOMORROW)

    class Meta:
        model = 'leadgalaxy.ShopifyStore'


class GroupPlanFactory(factory.django.DjangoModelFactory):
    stores = factory.fuzzy.FuzzyInteger(999)
    products = factory.fuzzy.FuzzyInteger(999)
    boards = factory.fuzzy.FuzzyInteger(999)
    sub_users_limit = factory.fuzzy.FuzzyInteger(999)
    register_hash = factory.fuzzy.FuzzyText(length=50)
    slug = factory.fuzzy.FuzzyText(length=10)
    default_plan = 1

    class Meta:
        model = 'leadgalaxy.GroupPlan'


class ShopifyOrderTrackFactory(factory.django.DjangoModelFactory):
    order_id = factory.fuzzy.FuzzyInteger(999)
    line_id = factory.fuzzy.FuzzyInteger(999)

    class Meta:
        model = 'leadgalaxy.ShopifyOrderTrack'


class AppPermissionFactory(factory.django.DjangoModelFactory):
    name = factory.fuzzy.FuzzyText(length=50)
    description = factory.fuzzy.FuzzyText(length=50)

    class Meta:
        model = 'leadgalaxy.AppPermission'


class ShopifyBoardFactory(factory.django.DjangoModelFactory):
    title = factory.fuzzy.FuzzyText(length=50)
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')

    class Meta:
        model = 'leadgalaxy.ShopifyBoard'


class ShopifyOrderFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('leadgalaxy.tests.factories.ShopifyStoreFactory')
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    order_id = factory.fuzzy.FuzzyInteger(99999999)
    order_number = factory.fuzzy.FuzzyInteger(999)
    total_price = factory.fuzzy.FuzzyFloat(1000.0)
    customer_id = factory.fuzzy.FuzzyInteger(999)
    items_count = 1
    customer_email = factory.LazyAttribute(lambda o: '%s@example.org' % o.user.username)
    created_at = factory.fuzzy.FuzzyDateTime(NOW, TOMORROW)
    updated_at = factory.fuzzy.FuzzyDateTime(NOW, TOMORROW)

    class Meta:
        model = 'shopify_orders.ShopifyOrder'


class ShopifyOrderLineFactory(factory.django.DjangoModelFactory):
    order = factory.SubFactory('leadgalaxy.tests.factories.ShopifyOrderFactory')
    line_id = factory.fuzzy.FuzzyInteger(99999999)
    shopify_product = factory.fuzzy.FuzzyInteger(99999999)
    price = factory.fuzzy.FuzzyFloat(1000.0)
    quantity = factory.fuzzy.FuzzyInteger(99)
    variant_id = factory.fuzzy.FuzzyInteger(99999999)

    class Meta:
        model = 'shopify_orders.ShopifyOrderLine'


class ShopifyOrderLogFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('leadgalaxy.tests.factories.ShopifyStoreFactory')
    order_id = factory.fuzzy.FuzzyInteger(99999999)

    class Meta:
        model = 'shopify_orders.ShopifyOrderLog'


class FeatureBundleFactory(factory.django.DjangoModelFactory):
    title = factory.fuzzy.FuzzyText()
    slug = factory.lazy_attribute(lambda b: slugify(b.title))
    register_hash = factory.fuzzy.FuzzyText()

    @factory.post_generation
    def permissions(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for permission in extracted:
                self.permissions.add(permission)

    class Meta:
        model = 'leadgalaxy.FeatureBundle'


class PlanRegistrationFactory(factory.django.DjangoModelFactory):
    plan = factory.SubFactory('leadgalaxy.tests.factories.GroupPlanFactory')
    bundle = factory.SubFactory('leadgalaxy.tests.factories.FeatureBundleFactory')

    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    sender = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    email = factory.LazyAttribute(lambda o: '%s@example.org' % o.user.username)
    register_hash = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'leadgalaxy.PlanRegistration'


class ProductChangeFactory(factory.django.DjangoModelFactory):
    shopify_product = factory.SubFactory('leadgalaxy.tests.factories.ShopifyProductFactory')

    class Meta:
        model = 'product_alerts.ProductChange'
