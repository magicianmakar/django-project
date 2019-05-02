import factory
import factory.fuzzy


class GrooveKartStoreFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    api_url = factory.fuzzy.FuzzyText()
    api_key = factory.fuzzy.FuzzyText()
    api_token = factory.fuzzy.FuzzyText()
    is_active = True

    class Meta:
        model = 'groovekart_core.GrooveKartStore'


class GrooveKartOrderTrackFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    store = factory.SubFactory('gearbubble_core.tests.factories.GrooveKartStoreFactory')
    order_id = factory.fuzzy.FuzzyInteger(1000)
    line_id = factory.fuzzy.FuzzyInteger(1000)

    class Meta:
        model = 'groovekart_core.GrooveKartOrderTrack'


class GrooveKartProductFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('groovekart_core.tests.factories.GrooveKartStoreFactory')
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    product_type = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'groovekart_core.GrooveKartProduct'


class ProductChangeFactory(factory.DjangoModelFactory):
    gkart_product = factory.SubFactory('groovekart_core.tests.factories.GrooveKartProductFactory')

    class Meta:
        model = 'product_alerts.ProductChange'
