import factory
import factory.fuzzy


class FeedStatusFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('leadgalaxy.tests.factories.ShopifyStoreFactory')

    class Meta:
        model = 'product_feed.FeedStatus'


class CommerceHQFeedStatusFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('commercehq_core.tests.factories.CommerceHQStoreFactory')

    class Meta:
        model = 'product_feed.CommerceHQFeedStatus'


class WooFeedStatusFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('woocommerce_core.tests.factories.WooStoreFactory')

    class Meta:
        model = 'product_feed.WooFeedStatus'


class GearBubbleFeedStatusFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('gearbubble_core.tests.factories.GearBubbleStoreFactory')

    class Meta:
        model = 'product_feed.GearBubbleFeedStatus'


class GrooveKartFeedStatusFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('groovekart_core.tests.factories.GrooveKartStoreFactory')

    class Meta:
        model = 'product_feed.GrooveKartFeedStatus'


class BigCommerceFeedStatusFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('bigcommerce_core.tests.factories.BigCommerceStoreFactory')

    class Meta:
        model = 'product_feed.BigCommerceFeedStatus'
