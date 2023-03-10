import factory
import factory.fuzzy


class WooStoreFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    api_url = factory.fuzzy.FuzzyText(prefix='https://', suffix='.com')
    api_key = factory.fuzzy.FuzzyText()
    api_password = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'woocommerce_core.WooStore'


class WooBoardFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    config = '{}'

    class Meta:
        model = 'woocommerce_core.WooBoard'


class WooProductFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('woocommerce_core.tests.factories.WooStoreFactory')
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'woocommerce_core.WooProduct'


class WooSupplierFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('woocommerce_core.tests.factories.WooStoreFactory')
    product = factory.SubFactory('woocommerce_core.tests.factories.WooProductFactory')

    class Meta:
        model = 'woocommerce_core.WooSupplier'


class WooOrderTrackFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    store = factory.SubFactory('woocommerce_core.tests.factories.WooStoreFactory')
    order_id = factory.fuzzy.FuzzyInteger(1000)
    line_id = factory.fuzzy.FuzzyInteger(1000)

    class Meta:
        model = 'woocommerce_core.WooOrderTrack'
