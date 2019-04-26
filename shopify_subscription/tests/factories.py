import factory
import factory.fuzzy


class ShopifySubscriptionFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    store = factory.SubFactory('leadgalaxy.tests.factories.ShopifyStoreFactory')
    plan = factory.SubFactory('leadgalaxy.tests.factories.GroupPlanFactory')
    subscription_id = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'shopify_subscription.ShopifySubscription'
