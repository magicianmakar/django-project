import factory
import factory.fuzzy


class AddonFactory(factory.DjangoModelFactory):
    monthly_price = factory.fuzzy.FuzzyDecimal(0.5, 42.7)

    class Meta:
        model = 'addons_core.Addon'


class AddonUsageFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    addon = factory.SubFactory('addons_core.tests.factories.AddonFactory')

    class Meta:
        model = 'addons_core.AddonUsage'
