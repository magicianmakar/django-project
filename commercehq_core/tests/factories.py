from django.utils import timezone

import factory
import factory.fuzzy


class CommerceHQStoreFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    api_url = factory.fuzzy.FuzzyText(prefix='https://', suffix='.commercehqdev.com')
    api_key = factory.fuzzy.FuzzyText()
    api_password = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'commercehq_core.CommerceHQStore'


class CommerceHQProductFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('commercehq_core.tests.factories.CommerceHQStoreFactory')
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    is_multi = False
    product_type = factory.fuzzy.FuzzyText()
    tags = ''
    created_at = timezone.now()
    updated_at = timezone.now()

    class Meta:
        model = 'commercehq_core.CommerceHQProduct'


class CommerceHQCollectionFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('commercehq_core.tests.factories.CommerceHQStoreFactory')
    collection_id = factory.fuzzy.FuzzyInteger(999)
    title = factory.fuzzy.FuzzyText()
    is_auto = False

    class Meta:
        model = 'commercehq_core.CommerceHQCollection'
