from django.utils import timezone

import factory
import factory.fuzzy


class CommerceHQStoreFactory(factory.DjangoModelFactory):
    url = factory.fuzzy.FuzzyText(prefix='https://', suffix='.commercehqdev.com')
    title = factory.fuzzy.FuzzyText()
    api_key = factory.fuzzy.FuzzyText()
    api_password = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'commercehq_core.CommerceHQStore'


class CommerceHQProductFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('commercehq_core.tests.factories.CommerceHQStoreFactory')
    product_id = factory.fuzzy.FuzzyInteger(999)
    title = factory.fuzzy.FuzzyText()
    is_multi = False
    product_type = factory.fuzzy.FuzzyText()
    textareas = '[]'
    shipping_weight = factory.fuzzy.FuzzyFloat(100.0)
    auto_fulfillment = False
    track_inventory = False
    tags = ''
    sku = factory.fuzzy.FuzzyText()
    seo_meta = factory.fuzzy.FuzzyText()
    seo_title = factory.fuzzy.FuzzyText()
    seo_url = factory.fuzzy.FuzzyText(prefix='https://', suffix='.commercehqdev.com')
    is_template = False
    template_name = factory.fuzzy.FuzzyText()
    is_draft = False
    created_at = timezone.now()
    updated_at = timezone.now()

    class Meta:
        model = 'commercehq_core.CommerceHQProduct'


class CommerceHQCollectionFactory(factory.DjangoModelFactory):
    store = factory.SubFactory('commercehq_core.tests.factories.CommerceHQStoreFactory')
    collection_id = factory.fuzzy.FuzzyInteger(999)
    title = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'commercehq_core.CommerceHQCollection'
