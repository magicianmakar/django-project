import factory
import factory.fuzzy


class CommerceHQStoreFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    api_url = factory.fuzzy.FuzzyText(prefix='https://', suffix='.commercehq.com')
    api_key = factory.fuzzy.FuzzyText()
    api_password = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'commercehq_core.CommerceHQStore'


class CommerceHQBoardFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    config = '{}'

    class Meta:
        model = 'commercehq_core.CommerceHQBoard'


class CommerceHQProductFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('commercehq_core.tests.factories.CommerceHQStoreFactory')
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    product_type = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'commercehq_core.CommerceHQProduct'


class CommerceHQSupplierFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('commercehq_core.tests.factories.CommerceHQStoreFactory')
    product = factory.SubFactory('commercehq_core.tests.factories.CommerceHQProductFactory')

    class Meta:
        model = 'commercehq_core.CommerceHQSupplier'


class CommerceHQOrderTrackFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    order_id = factory.fuzzy.FuzzyInteger(999)
    line_id = factory.fuzzy.FuzzyInteger(999)

    class Meta:
        model = 'commercehq_core.CommerceHQOrderTrack'


class ProductChangeFactory(factory.django.DjangoModelFactory):
    chq_product = factory.SubFactory('commercehq_core.tests.factories.CommerceHQProductFactory')

    class Meta:
        model = 'product_alerts.ProductChange'
