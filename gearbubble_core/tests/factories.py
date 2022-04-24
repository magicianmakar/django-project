import factory
import factory.fuzzy


class GearBubbleStoreFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    api_token = factory.fuzzy.FuzzyText()
    is_active = True

    class Meta:
        model = 'gearbubble_core.GearBubbleStore'


class GearBubbleBoardFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    config = '{}'

    class Meta:
        model = 'gearbubble_core.GearBubbleBoard'


class GearBubbleProductFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('gearbubble_core.tests.factories.GearBubbleStoreFactory')
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    product_type = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'gearbubble_core.GearBubbleProduct'


class GearBubbleSupplierFactory(factory.django.DjangoModelFactory):
    store = factory.SubFactory('gearbubble_core.tests.factories.GearBubbleStoreFactory')
    product = factory.SubFactory('gearbubble_core.tests.factories.GearBubbleProductFactory')

    class Meta:
        model = 'gearbubble_core.GearBubbleSupplier'


class GearBubbleOrderTrackFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    store = factory.SubFactory('gearbubble_core.tests.factories.GearBubbleStoreFactory')
    order_id = factory.fuzzy.FuzzyInteger(1000)
    line_id = factory.fuzzy.FuzzyInteger(1000)

    class Meta:
        model = 'gearbubble_core.GearBubbleOrderTrack'
