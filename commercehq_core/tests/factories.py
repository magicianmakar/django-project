import factory
import factory.fuzzy


class CommerceHQStoreFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    api_url = factory.fuzzy.FuzzyText(prefix='https://', suffix='.commercehq.com')
    api_key = factory.fuzzy.FuzzyText()
    api_password = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'commercehq_core.CommerceHQStore'


class CommerceHQBoardFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    config = '{}'

    class Meta:
        model = 'commercehq_core.CommerceHQBoard'


class CommerceHQProductFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('commercehq_core.tests.factories.CommerceHQStoreFactory')
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    product_type = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'commercehq_core.CommerceHQProduct'


class CommerceHQSupplierFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('commercehq_core.tests.factories.CommerceHQStoreFactory')
    product = factory.SubFactory('commercehq_core.tests.factories.CommerceHQProductFactory')

    class Meta:
        model = 'commercehq_core.CommerceHQSupplier'


class CommerceHQOrderTrackFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    order_id = factory.fuzzy.FuzzyInteger(999)
    line_id = factory.fuzzy.FuzzyInteger(999)

    class Meta:
        model = 'commercehq_core.CommerceHQOrderTrack'
