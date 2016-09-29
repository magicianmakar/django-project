import factory
import factory.fuzzy


class StripeCustomerFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    customer_id = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'stripe_subscription.StripeCustomer'

