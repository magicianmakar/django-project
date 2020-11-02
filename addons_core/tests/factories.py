import arrow
import datetime
import factory
import factory.fuzzy
from django.contrib.auth.models import User

from stripe_subscription.models import StripeCustomer, StripeSubscription
from addons_core.utils import DictAsObject


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
    slug = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'addons_core.Addon'


class AddonPriceFactory(factory.DjangoModelFactory):
    price = factory.fuzzy.FuzzyDecimal(0.1)

    class Meta:
        model = 'addons_core.AddonPrice'


class AddonBillingFactory(factory.DjangoModelFactory):
    addon = factory.SubFactory('addons_core.tests.factories.AddonFactory')
    prices = factory.RelatedFactory(AddonPriceFactory, factory_related_name='billing')
    interval = 2

    class Meta:
        model = 'addons_core.AddonBilling'


class AddonUsageFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('addons_core.tests.factories.UserFactory')
    billing = factory.SubFactory('addons_core.tests.factories.AddonBillingFactory')

    class Meta:
        model = 'addons_core.AddonUsage'

    @factory.post_generation
    def add_addon_to_user(self, create, extracted, **kwargs):
        if create:
            self.billing.addon.userprofile_set.add(self.user.profile)
            self.user.profile.plan.support_addons = True
            self.user.profile.plan.save()


class StripeProductFactory(factory.Factory):
    id = factory.fuzzy.FuzzyText(length=14, prefix='Addon_')
    name = factory.fuzzy.FuzzyText()
    description = ''
    active = True
    images = []
    metadata = {'type': 'addon'}

    class Meta:
        model = DictAsObject
        abstract = False


class StripePriceFactory(factory.Factory):
    id = factory.fuzzy.FuzzyText(length=19, prefix='AddonPrice_')
    unit_amount = factory.fuzzy.FuzzyDecimal(low=100)  # unit in cents
    recurring = DictAsObject({
        'interval': 'month',
        'interval_count': 1,
        'trial_period_days': 0,
    })
    metadata = DictAsObject({'type': 'addon'})
    active = True

    class Meta:
        model = DictAsObject
        abstract = False


class StripeSubscriptionItemFactory(factory.Factory):
    id = factory.fuzzy.FuzzyText(length=8)
    price = StripePriceFactory()

    class Meta:
        model = DictAsObject
        abstract = False


class StripeSubscriptionFactory(factory.Factory):
    id = factory.fuzzy.FuzzyText(length=8)
    items = {'data': [StripeSubscriptionItemFactory()]}
    billing_cycle_anchor = factory.fuzzy.FuzzyDate(datetime.date(2020, 1, 1))
    current_period_start = factory.fuzzy.FuzzyDate(datetime.date(2020, 1, 1))
    current_period_end = factory.fuzzy.FuzzyDate(datetime.date(2020, 1, 1))

    class Meta:
        model = DictAsObject
        abstract = False
