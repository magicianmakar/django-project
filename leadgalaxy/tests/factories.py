import datetime
from django.conf import settings
from django.utils import timezone

import factory
import factory.fuzzy

NOW = timezone.now()
TOMORROW = NOW + datetime.timedelta(days=1)


class UserFactory(factory.DjangoModelFactory):
    username = factory.fuzzy.FuzzyText()
    first_name = factory.fuzzy.FuzzyText()
    last_name = factory.fuzzy.FuzzyText()
    is_active = True

    class Meta:
        model = settings.AUTH_USER_MODEL


class UserProfileFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    subuser_parent = None
    stores = factory.fuzzy.FuzzyInteger(999)
    products = factory.fuzzy.FuzzyInteger(999)
    boards = factory.fuzzy.FuzzyInteger(999)

    class Meta:
        model = 'leadgalaxy.UserProfile'


class ShopifyProductFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('leadgalaxy.tests.factories.ShopifyStoreFactory')
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    data = '{}'
    price = factory.fuzzy.FuzzyFloat(100.0)
    monitor_id = factory.fuzzy.FuzzyInteger(999)
    created_at = factory.fuzzy.FuzzyDateTime(NOW, TOMORROW)
    updated_at = factory.fuzzy.FuzzyDateTime(NOW, TOMORROW)

    class Meta:
        model = 'leadgalaxy.ShopifyProduct'


class ProductSupplierFactory(factory.DjangoModelFactory):
    product = factory.SubFactory('leadgalaxy.tests.factories.ShopifyProduct')

    class Meta:
        model = 'leadgalaxy.ProductSupplier'


class ShopifyStoreFactory(factory.DjangoModelFactory):
    title = factory.fuzzy.FuzzyText()
    api_url = factory.fuzzy.FuzzyText(prefix='https://', suffix='.myshopify.com')
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


class GroupPlanFactory(factory.DjangoModelFactory):
    stores = factory.fuzzy.FuzzyInteger(999)
    products = factory.fuzzy.FuzzyInteger(999)
    boards = factory.fuzzy.FuzzyInteger(999)
    register_hash = factory.fuzzy.FuzzyText(length=50)
    default_plan = 1

    class Meta:
        model = 'leadgalaxy.GroupPlan'


class ShopifyOrderTrackFactory(factory.DjangoModelFactory):
    order_id = factory.fuzzy.FuzzyInteger(999)
    line_id = factory.fuzzy.FuzzyInteger(999)

    class Meta:
        model = 'leadgalaxy.ShopifyOrderTrack'


class AppPermissionFactory(factory.DjangoModelFactory):
    name = factory.fuzzy.FuzzyText(length=50)
    description = factory.fuzzy.FuzzyText(length=50)

    class Meta:
        model = 'leadgalaxy.AppPermission'


class ShopifyOrderFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('leadgalaxy.tests.factories.ShopifyStoreFactory')
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    order_id = factory.fuzzy.FuzzyInteger(99999999)
    order_number = factory.fuzzy.FuzzyInteger(999)
    total_price = factory.fuzzy.FuzzyFloat(1000.0)
    customer_id = factory.fuzzy.FuzzyInteger(999)
    customer_email = factory.LazyAttribute(lambda o: '%s@example.org' % o.user.username)
    created_at = factory.fuzzy.FuzzyDateTime(NOW, TOMORROW)
    updated_at = factory.fuzzy.FuzzyDateTime(NOW, TOMORROW)

    class Meta:
        model = 'shopify_orders.ShopifyOrder'
