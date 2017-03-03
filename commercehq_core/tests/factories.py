from django.utils import timezone

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

    class Meta:
        model = 'commercehq_core.CommerceHQBoard'


class CommerceHQProductFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('commercehq.tests.factories.CommerceHQStoreFactory')
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    product_type = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'commercehq_core.CommerceHQProduct'
