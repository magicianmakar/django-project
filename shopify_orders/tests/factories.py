import datetime

from django.utils import timezone

import factory
import factory.fuzzy

NOW = timezone.now()
TOMORROW = NOW + datetime.timedelta(days=1)


class ShopifyOrderFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    store = factory.SubFactory('leadgalaxy.tests.factories.ShopifyStoreFactory')
    order_id = factory.fuzzy.FuzzyInteger(400000000, 500000000)
    country_code = 'US'
    order_number = factory.fuzzy.FuzzyInteger(1000)
    total_price = factory.fuzzy.FuzzyFloat(1000000.00)
    customer_id = factory.fuzzy.FuzzyInteger(1000000)
    created_at = factory.fuzzy.FuzzyDateTime(NOW, TOMORROW)
    updated_at = factory.fuzzy.FuzzyDateTime(NOW, TOMORROW)

    class Meta:
        model = 'shopify_orders.ShopifyOrder'
