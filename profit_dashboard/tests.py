from datetime import datetime, timedelta
from dateutil.parser import parse as date_parser
from random import randint

from django.conf import settings
from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone

from facebookads.api import FacebookAdsApi
from facebookads.adobjects.user import User
from facebookads.adobjects.campaign import Campaign

from leadgalaxy.tests import factories as f

from .models import FacebookInsight, ShopifyProfit
from .utils import get_facebook_ads, get_facebook_profit, calculate_shopify_profit


class FacebookInsightsTestCase(TestCase):
    def setUp(self):
        self.user = f.UserFactory(username='test')
        self.user.save()

        self.access_token = "EAASor7q5H9wBAOAjZAZCO2rq37IMXBtHWwMvMoemvQjGC1F4AoOs" + \
            "3AN8GZCVQczR4qn9TPXs7k7ZAeuKSZBoqINGTibOI8rFtKfd1oksn5DxsLXXpkuv" + \
            "V6MBYhZAD0ZBmDy2CQMZAdshZCv3FGIefW3XZBfbbNKHxsbOZBRNrrIGZAWU9Wqg" + \
            "cdbVRhchEIIz2X5vOHBjsZAb15vIC9oScj4ZAF7xx5"

        self.api = FacebookAdsApi.init(
            settings.FACEBOOK_APP_ID,
            settings.FACEBOOK_APP_SECRET,
            self.access_token
        )

        user = User(fbid='me', api=self.api)
        account = list(user.get_ad_accounts())[0]

        campaigns = account.get_campaigns(fields=[Campaign.Field.created_time])
        create = True
        now = timezone.now()
        current_month = now - timedelta(days=now.day - 1)
        for campaign in campaigns:
            created = date_parser(campaign[Campaign.Field.created_time])
            if created > current_month:
                create = False

        if create:
            campaign = Campaign(parent_id=account.get_id_assured())
            campaign[Campaign.Field.name] = "Companies looking for profit can come here"
            campaign[Campaign.Field.objective] = "REACH"
            campaign[Campaign.Field.configured_status] = Campaign.Status.paused
            campaign.remote_create()

    def test_more_than_one_insight_exists_for_user(self):
        get_facebook_ads(self.user, self.access_token)

        self.assertGreater(FacebookInsight.objects.count(), 0)

    def test_insight_dict_has_right_keys(self):
        get_facebook_ads(self.user, self.access_token)
        insights = get_facebook_profit(self.user.id, datetime.now() - timedelta(days=30), datetime.now())

        self.assertItemsEqual(
            insights.items()[0][1].keys(),
            ['revenue', 'fulfillment_cost', 'ad_spend', 'other_costs']
        )


class ProfitSyncTestCase(TestCase):
    def setUp(self):
        self.user = f.UserFactory(username='test')
        self.user.save()

        self.store = f.ShopifyStoreFactory(user=self.user)
        self.store.save()

        self.price_by_day = {}
        self.start_date = timezone.now() - timedelta(days=60)
        self.end_date = self.start_date + timedelta(days=30)
        for day in range((self.end_date - self.start_date).days):
            date = self.start_date + timedelta(days=day)
            date_string = date.strftime('%m/%d/%Y')

            for times in range(randint(2, 5)):
                shopify_order = f.ShopifyOrderFactory(
                    user=self.user,
                    store=self.store,
                    created_at=date,
                    updated_at=date
                )
                shopify_order.save()
                self.price_by_day[date_string] = self.price_by_day.get(date_string, 0.0) + shopify_order.total_price

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    def test_revenue_is_merging_properly(self):
        run_calculation = calculate_shopify_profit(
            self.user.id,
            self.store.id,
            self.start_date,
            self.end_date
        )
        self.assertTrue(run_calculation)
        for profit in ShopifyProfit.objects.filter(date__range=(self.start_date, self.end_date)):
            self.assertEqual(profit.revenue, self.price_by_day.get(profit.date.strftime('%m/%d/%Y'), 0))


"""
user = User.objects.get(username='admin')
store = ShopifyStore.objects.get(title='Uncommon Now')
price_by_day = {}
start_date = timezone.now() - timedelta(days=60)
end_date = start_date + timedelta(days=30)
for day in range((end_date - start_date).days):
    date = start_date + timedelta(days=day)
    date_string = date.strftime('%m/%d/%Y')

    for times in range(randint(2, 5)):
        shopify_order = f.ShopifyOrderFactory(
            user=user,
            store=store,
            created_at=date,
            updated_at=date
        )
        shopify_order.save()
        price_by_day[date_string] = price_by_day.get(date_string, 0.0) + shopify_order.total_price

    print date_string, ': imported ', times, 'times'
"""
