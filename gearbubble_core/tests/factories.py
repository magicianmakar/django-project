import factory
import factory.fuzzy


class GearBubbleStoreFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    api_token = factory.fuzzy.FuzzyText()
    is_active = True

    class Meta:
        model = 'gearbubble_core.GearBubbleStore'


class GearBubbleOrderTrackFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    store = factory.SubFactory('gearbubble_core.tests.factories.GearBubbleStoreFactory')
    order_id = factory.fuzzy.FuzzyInteger(1000)
    line_id = factory.fuzzy.FuzzyInteger(1000)

    class Meta:
        model = 'gearbubble_core.GearBubbleOrderTrack'
