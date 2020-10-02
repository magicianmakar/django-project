import arrow
import factory
import factory.fuzzy
from django.contrib.auth.models import User

from stripe_subscription.models import StripeCustomer, StripeSubscription


class StripeSubscriptionFactory(factory.DjangoModelFactory):
    subscription_id = factory.fuzzy.FuzzyText()
    period_start = factory.fuzzy.FuzzyDateTime(arrow.get('2020-01-01').datetime)

    class Meta:
        model = StripeSubscription


class StripeCustomerFactory(factory.DjangoModelFactory):
    customer_id = factory.fuzzy.FuzzyText()

    class Meta:
        model = StripeCustomer


class UserFactory(factory.DjangoModelFactory):
    id = factory.fuzzy.FuzzyInteger(999)
    username = factory.fuzzy.FuzzyText()
    first_name = factory.fuzzy.FuzzyText()
    last_name = factory.fuzzy.FuzzyText()
    is_active = True

    stripecustomer = factory.RelatedFactory(
        StripeCustomerFactory,
        factory_related_name='user',
    )

    stripesubscription = factory.RelatedFactory(
        StripeSubscriptionFactory,
        factory_related_name='user',
        plan=factory.SelfAttribute('user.profile.plan')
    )

    class Meta:
        model = User
        django_get_or_create = ['id']


class AddonFactory(factory.DjangoModelFactory):
    monthly_price = factory.fuzzy.FuzzyDecimal(0.5, 42.7)
    slug = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'addons_core.Addon'


class AddonUsageFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('addons_core.tests.factories.UserFactory')
    addon = factory.SubFactory('addons_core.tests.factories.AddonFactory')
    billing_day = factory.fuzzy.FuzzyInteger(1, 31)

    class Meta:
        model = 'addons_core.AddonUsage'

    @factory.post_generation
    def add_addon_to_user(self, create, extracted, **kwargs):
        if create:
            self.addon.userprofile_set.add(self.user.profile)
            self.user.profile.plan.support_addons = True
            self.user.profile.plan.save()
