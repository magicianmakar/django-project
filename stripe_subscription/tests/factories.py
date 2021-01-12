import factory
import factory.fuzzy


class StripeCustomerFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    customer_id = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'stripe_subscription.StripeCustomer'


class StripePlanFactory(factory.DjangoModelFactory):
    name = factory.fuzzy.FuzzyText()
    plan = factory.SubFactory('leadgalaxy.tests.factories.GroupPlanFactory')
    amount = factory.fuzzy.FuzzyDecimal(0.00, 1000.00, 2)
    stripe_id = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'stripe_subscription.StripePlan'
