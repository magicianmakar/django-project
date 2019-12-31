import factory
import factory.fuzzy


class FeedStatusFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('leadgalaxy.tests.factories.ShopifyStoreFactory')

    class Meta:
        model = 'product_feed.FeedStatus'


class CommerceHQFeedStatusFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('commercehq_core.tests.factories.CommerceHQStoreFactory')

    class Meta:
        model = 'product_feed.CommerceHQFeedStatus'


class WooFeedStatusFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('woocommerce_core.tests.factories.WooStoreFactory')

    class Meta:
        model = 'product_feed.WooFeedStatus'


class GearBubbleFeedStatusFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('gearbubble_core.tests.factories.GearBubbleStoreFactory')

    class Meta:
        model = 'product_feed.GearBubbleFeedStatus'


class GrooveKartFeedStatusFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('groovekart_core.tests.factories.GrooveKartStoreFactory')

    class Meta:
        model = 'product_feed.GrooveKartFeedStatus'


class BigCommerceFeedStatusFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('bigcommerce_core.tests.factories.BigCommerceStoreFactory')

    class Meta:
        model = 'product_feed.BigCommerceFeedStatus'
