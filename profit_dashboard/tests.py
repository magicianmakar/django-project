import simplejson as json
import uuid
from datetime import timedelta
from dateutil.parser import parse as date_parser
from random import randint
from urllib.parse import urlencode

import factory
import factory.fuzzy

from django.test import tag
from django.test.client import RequestFactory
from django.urls import reverse
from django.utils import timezone
from django.db.models import Sum
from lib.test import BaseTestCase
from unittest.mock import patch, Mock

from facebook_business.adobjects.user import User as FBUser
from facebook_business.adobjects.campaign import Campaign
from facebook_business.exceptions import FacebookRequestError

from leadgalaxy.tests import factories as f
from shopify_orders.models import ShopifyOrder
from shopify_orders.tests.factories import ShopifyOrderFactory

from .models import AliexpressFulfillmentCost
from .utils import get_facebook_ads, get_profits, get_date_range


NOW = timezone.now()
YESTERDAY = NOW - timedelta(days=1)


class FacebookAccessFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    store = factory.SubFactory('leadgalaxy.tests.factories.ShopifyStoreFactory')
    access_token = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'profit_dashboard.FacebookAccess'


class FacebookAccountFactory(factory.DjangoModelFactory):
    access = factory.SubFactory('profit_dashboard.tests.FacebookAccessFactory')
    store = factory.SubFactory('leadgalaxy.tests.factories.ShopifyStoreFactory')
    last_sync = factory.fuzzy.FuzzyDateTime(YESTERDAY, NOW)
    account_id = factory.fuzzy.FuzzyText(prefix='act_')
    account_name = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'profit_dashboard.FacebookAccount'


class FacebookAdCostFactory(factory.DjangoModelFactory):
    account = factory.SubFactory('profit_dashboard.tests.FacebookAccountFactory')
    spend = factory.fuzzy.FuzzyFloat(100.0)
    created_at = factory.fuzzy.FuzzyDateTime(YESTERDAY, NOW)

    class Meta:
        model = 'profit_dashboard.FacebookAdCost'


class FacebookAdCostsTestCase(BaseTestCase):
    def setUp(self):
        self.user = f.UserFactory(username='test')
        self.user.save()
        self.store = f.ShopifyStoreFactory(
            user=self.user,
            api_url='https://:88937df17024aa5126203507e2147f47@shopified-app-ci.myshopify.com'
        )
        self.store.save()

        self.access_token = "EAASor7q5H9wBABZBD1kZBZBnCStlWnU2RAbxGZCu5swK1v7F5W6o" + \
            "5UcAmKMR4z0T2lFNmhwSS6tWkXkifsMZA1aX2sYkBZBDZCqnbqIw8oCJgKn5ZBVC2jOHt" + \
            "zeTuuiBtBWNcc40zZCkn589nxHptuO54I3DoRLk8fqh5skJZA76mboZAAlYYUQDTAhIpc" + \
            "eYZA7JLHODWNEj6JDqhJfZB8y12ARYp7k6vOeB27h0ZD"
        access = FacebookAccessFactory(store=self.store, user=self.user, access_token=self.access_token,
                                       expires_in=timezone.now() + timedelta(days=59))

        try:
            self.api = access.api

            user = FBUser(fbid='me', api=self.api)
            account = list(user.get_ad_accounts())[0]

            campaigns = account.get_campaigns(fields=[Campaign.Field.created_time])
            create = True
            now = timezone.now()
            current_month = now - timedelta(days=now.day - 1)
            selected_campaigns = []
            for campaign in campaigns:
                selected_campaigns.append(campaign[Campaign.Field.id])
                created = date_parser(campaign[Campaign.Field.created_time])
                if created > current_month:
                    create = False

            if create:
                self.api.set_default_account_id(account.get_id_assured())
                campaign = Campaign()
                campaign[Campaign.Field.name] = "Companies looking for profit can come here"
                campaign[Campaign.Field.objective] = "REACH"
                campaign[Campaign.Field.configured_status] = Campaign.Status.paused
                campaign.remote_create()
                campaigns = account.get_campaigns(fields=[Campaign.Field.created_time])
                selected_campaigns = [c[Campaign.Field.id] for c in campaigns]

            get_facebook_ads(access.pk, self.store)
        except FacebookRequestError as e:
            if e.api_error_code() == 17:  # (#17) User request limit reached
                account = FacebookAccountFactory(access=access, store=self.store)
                FacebookAdCostFactory(account=account)

    # def test_more_than_one_ad_cost_exists_for_user(self):
    #     self.assertGreater(FacebookAdCost.objects.count(), 0)

    @tag('slow')
    def test_ad_costs_dict_has_right_keys(self):
        profits, totals, details = get_profits(self.store, timezone.now() - timedelta(days=30), timezone.now())

        self.assertListEqual(
            sorted(profits[0].keys()),
            sorted('date_as_string,date_as_slug,week_day,empty,css_empty,revenue,fulfillment_cost,fulfillments_count,'
                   'orders_count,ad_spend,other_costs,outcome,profit'.split(','))
        )


class RevenueTestCase(BaseTestCase):
    def setUp(self):
        self.user = f.UserFactory()
        self.store = f.ShopifyStoreFactory(
            user=self.user,
            api_url='https://:88937df17024aa5126203507e2147f47@shopified-app-ci.myshopify.com'
        )
        self.time = timezone.now()
        for i in range(10):
            o = ShopifyOrderFactory(store=self.store, created_at=self.time + timedelta(days=i))
            o.financial_status = 'paid'
            o.save()

        end = self.time + timedelta(9)
        self.profits, self.totals, details = get_profits(self.store, self.time, end)

    @tag('slow')
    def test_revenue_by_day_is_correct(self):
        i = 0
        for order in ShopifyOrder.objects.all().order_by('-created_at'):
            self.assertAlmostEqual(self.profits[i]['revenue'], float(order.total_price))
            i += 1

    @tag('slow')
    def test_total_revenue_is_correct(self):
        total_revenue = ShopifyOrder.objects.all().aggregate(total=Sum('total_price'))['total']
        self.assertAlmostEqual(self.totals['revenue'], total_revenue)


class FulfillmentCostTestCase(BaseTestCase):
    def setUp(self):
        self.user = f.UserFactory()
        self.store = f.ShopifyStoreFactory(
            user=self.user,
            api_url='https://:88937df17024aa5126203507e2147f47@shopified-app-ci.myshopify.com'
        )
        time = timezone.now()
        self.now = timezone.now()
        self.total = 0.0
        for i in range(10):
            time = self.now + timedelta(days=i)
            with patch('django.utils.timezone.now', Mock(return_value=time)):  # mock auto_now_add=True
                amount = randint(100, 1000)
                self.total += amount
                f.ShopifyOrderTrackFactory(
                    store=self.store,
                    user=self.user,
                    source_id=uuid.uuid4().hex,
                    data=json.dumps({'aliexpress': {'order_details': {'cost': {'total': amount}}, 'end_reason': ''}})
                )

        end = self.now + timedelta(9)
        self.profits, self.totals, details = get_profits(self.store, self.now, end)

    @tag('slow')
    def test_fulfillment_cost_by_day_is_correct(self):
        i = 0
        for fulfillment_cost in AliexpressFulfillmentCost.objects.all().order_by('-created_at'):
            self.assertAlmostEqual(self.profits[i]['fulfillment_cost'], float(fulfillment_cost.total_cost))
            i += 1

    @tag('slow')
    def test_total_fulfillment_cost_is_correct(self):
        # total_fulfillment_cost = AliexpressFulfillmentCost.objects.all().aggregate(total=Sum('total_cost'))['total']
        # self.assertAlmostEqual(self.totals['fulfillment_cost'], total_fulfillment_cost)
        pass


class SearchTestCase(BaseTestCase):
    def setUp(self):
        params = (('date_range', '03/01/2020-04/01/2020'),)
        self.request = RequestFactory().get(f"{reverse('profit_dashboard.views.index')}?{urlencode(params)}")

    def test_sould_apply_daylight_savings(self):
        store_timezone = 'Europe/Paris'
        start, end = get_date_range(self.request, store_timezone)
        self.assertEqual(start.strftime('%z'), '+0100')
        self.assertEqual(end.strftime('%z'), '+0200')
