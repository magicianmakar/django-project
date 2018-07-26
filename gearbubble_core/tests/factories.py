import factory
import factory.fuzzy


class GearBubbleStoreFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()
    api_token = factory.fuzzy.FuzzyText()
    is_active = True

    class Meta:
        model = 'gearbubble_core.GearBubbleStore'
