import factory
import factory.fuzzy


class BigCommerceStoreFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    api_url = factory.fuzzy.FuzzyText(suffix='.mybigcommerce.com')
    api_key = factory.fuzzy.FuzzyText()
    api_token = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'bigcommerce_core.BigCommerceStore'


class BigCommerceBoardFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    config = '{}'

    class Meta:
        model = 'bigcommerce_core.BigCommerceBoard'


class BigCommerceProductFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('bigcommerce_core.tests.factories.BigCommerceStoreFactory')
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'bigcommerce_core.BigCommerceProduct'


class BigCommerceSupplierFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('bigcommerce_core.tests.factories.BigCommerceStoreFactory')
    product = factory.SubFactory('bigcommerce_core.tests.factories.BigCommerceProductFactory')

    class Meta:
        model = 'bigcommerce_core.BigCommerceSupplier'


class BigCommerceOrderTrackFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    store = factory.SubFactory('bigcommerce_core.tests.factories.BigCommerceStoreFactory')
    order_id = factory.fuzzy.FuzzyInteger(1000)
    line_id = factory.fuzzy.FuzzyInteger(1000)

    class Meta:
        model = 'bigcommerce_core.BigCommerceOrderTrack'
