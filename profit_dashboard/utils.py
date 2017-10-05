import arrow
from datetime import timedelta, date
from collections import OrderedDict
from math import ceil

from django.conf import settings
from django.utils.text import slugify
from django.db.models import Value, CharField, Q, Count
from django.db.models.functions import Concat

from facebookads.api import FacebookAdsApi
from facebookads.adobjects.user import User as FBUser
from facebookads.adobjects.adaccount import AdAccount

from leadgalaxy.models import ShopifyOrderTrack
from shopify_orders.models import ShopifyOrder

from .models import (
    FacebookAccess,
    FacebookAccount,
    FacebookInsight,
    ShopifyProfit,
)
from .tasks import cache_shopify_profits


def get_meta(start, end, current_page, limit):
    delta = end - start
    max_results = delta.days
    if limit is not None:
        pages = range(1, int(ceil((max_results + 1) / float(limit))) + 1)

        page_start = limit * (current_page - 1)
        start = start + timedelta(days=page_start)

        page_end = start + timedelta(days=limit - 1)
        if page_end < end:
            end = page_end
    else:
        pages = [1]

    return {'start': start, 'end': end, 'max_results': max_results, 'pages': pages}


def initialize_base_dict(start, end):
    result = OrderedDict()
    delta = end - start

    for days in range(delta.days + 1):
        day = start + timedelta(days=days)
        string_day = day.strftime('%m/%d/%Y')
        result[string_day] = {
            'date_as_string': string_day,
            'date_as_slug': slugify(string_day),
            'week_day': day.strftime('%A'),
            'empty': True,
            'css_empty': 'empty',
            'item': {
                'revenue': 0.0,
                'fulfillment_cost': 0.0,
                'ad_spend': 0.0,
                'other_costs': 0.0,
                'outcome': 0.0,
                'profit': 0.0
            }
        }

    return result


def merge_profits(data, result):
    totals = {'revenue': 0.0, 'fulfillment_cost': 0.0, 'ad_spend': 0.0,
              'other_costs': 0.0, 'outcome': 0.0, 'profit': 0.0, 'orders_count': 0}

    for source in data:
        for date_key, items in source.items():
            revenue = float(items.get('revenue', 0.0))
            fulfillment_cost = float(items.get('fulfillment_cost', 0.0))
            ad_spend = float(items.get('ad_spend', 0.0))
            other_costs = float(items.get('other_costs', 0.0))
            orders_count = items.get('orders_count', 0)

            totals['revenue'] += revenue
            totals['fulfillment_cost'] += fulfillment_cost
            totals['ad_spend'] += ad_spend
            totals['other_costs'] += other_costs
            totals['orders_count'] += orders_count

            outcome = fulfillment_cost + ad_spend + other_costs
            totals['outcome'] += outcome
            totals['profit'] += revenue - outcome

            # Don't populate dates not being shown
            if date_key not in result:
                continue

            result[date_key]['empty'] = False
            result[date_key]['css_empty'] = ''
            result[date_key]['item']['revenue'] += revenue
            result[date_key]['item']['fulfillment_cost'] += fulfillment_cost
            result[date_key]['item']['ad_spend'] += ad_spend
            result[date_key]['item']['other_costs'] += other_costs

            result[date_key]['item']['outcome'] += result[date_key]['item']['fulfillment_cost'] + \
                result[date_key]['item']['ad_spend'] + result[date_key]['item']['other_costs']
            result[date_key]['item']['profit'] += result[date_key]['item']['revenue'] - \
                result[date_key]['item']['outcome']

            if result[date_key]['item']['revenue'] == 0 or \
                    revenue < result[date_key]['item']['profit'] or \
                    result[date_key]['item']['profit'] < 0:
                percentage = 0
            else:
                percentage = result[date_key]['item']['profit'] / result[date_key]['item']['revenue'] * 100
            result[date_key]['item']['return_over_investment'] = '{}%'.format(int(percentage))

    return result.values()[::-1], totals


def get_shopify_profit(store_id, start_date, end_date):
    # Get data from cached shopify profits
    profits = ShopifyProfit.objects.filter(
        store_id=store_id,
        date__range=(start_date, end_date)
    ).annotate(orders_count=Count('imported_orders'))

    return {
        profit.date.strftime('%m/%d/%Y'): {
            'revenue': profit.revenue,
            'fulfillment_cost': profit.fulfillment_cost,
            'other_costs': profit.other_costs,
            'orders_count': profit.orders_count,
        } for profit in profits
    }


def get_facebook_profit(user_id, store_id, start_date, end_date):
    access = FacebookAccess.objects.filter(user_id=user_id, store_id=store_id)

    if not access.exists():
        return {}
    else:
        access = access.first()

    result = {}
    for account in access.accounts.all():
        for insight in account.insights.filter(date__range=(start_date, end_date)):
            date_key = insight.date.strftime('%m/%d/%Y')

            if date_key in result:
                result[date_key]['ad_spend'] += insight.spend
            else:
                result[date_key] = {
                    'revenue': 0.0,
                    'fulfillment_cost': 0.0,
                    'ad_spend': float(insight.spend),
                    'other_costs': 0.0
                }

    return result


def get_facebook_ads(user, store, access_token=None, account_ids=None, campaigns=None):
    access, created = FacebookAccess.objects.get_or_create(user=user, store=store, defaults={
        'access_token': access_token,
        'account_ids': ','.join(account_ids) if account_ids else '',
        'campaigns': ','.join(campaigns) if campaigns else '',
    })

    if access_token and access_token != access.access_token:
        access.access_token = access_token
        access.save()

    if not account_ids:
        account_ids = access.account_ids.split(',') if access.account_ids else []

    if not campaigns:
        campaigns = access.campaigns.split(',') if access.campaigns else []

    api = FacebookAdsApi.init(
        settings.FACEBOOK_APP_ID,
        settings.FACEBOOK_APP_SECRET,
        access_token
    )

    user = FBUser(fbid='me', api=api)
    accounts = user.get_ad_accounts(fields=[AdAccount.Field.name])
    params = {'time_increment': 1}

    for account in accounts:
        if account['id'] not in account_ids:
            continue

        account_model, created = FacebookAccount.objects.get_or_create(
            account_id=account.get(account.Field.id),
            access=access,
            store=store,
            defaults={
                'account_name': account.get(account.Field.name),
                'last_sync': date.today()
            }
        )

        if account_model.last_sync:
            params['time_range'] = {
                'since': account_model.last_sync.strftime('%Y-%m-%d'),
                'until': date.today().strftime('%Y-%m-%d')
            }

        campaign_insights = {}
        for campaign in account.get_campaigns(fields=['name', 'status', 'created_time']):
            if campaign['id'] not in campaigns:
                continue

            for insight in campaign.get_insights(params=params):
                insight_date = arrow.get(insight[insight.Field.date_start]).datetime
                if insight_date not in campaign_insights:
                    campaign_insights[insight_date] = {
                        'impressions': int(insight[insight.Field.impressions]),
                        'spend': float(insight[insight.Field.spend]),
                    }
                else:
                    campaign_insights[insight_date]['impressions'] += int(insight[insight.Field.impressions])
                    campaign_insights[insight_date]['spend'] += float(insight[insight.Field.spend])

        for key, val in campaign_insights.items():
            FacebookInsight.objects.update_or_create(account=account_model, date=key, defaults=val)

        account_model.last_sync = date.today()
        account_model.save()


def calculate_shopify_profit(store_id, start_date, end_date):
    """
    Calculates if there is any need for profits to be synced
    Used only for revenue and fulfillment cost
    5 queries are done to reduce payload on task

    :param store_id: id from shopify store to be synced
    :param start_date: starting date object from page search criteria
    :param end_date: ending date object from page search criteria
    """
    date_range = (start_date, end_date)
    profit_search = ShopifyProfit.objects.filter(
        store_id=store_id,
        date__range=date_range
    )

    imported_order_ids = list(profit_search.values_list('imported_orders__order_id', flat=True).distinct())
    shopify_orders = ShopifyOrder.objects.filter(store_id=store_id, created_at__range=date_range)
    found_orders = [x.order_id for x in shopify_orders if x.order_id not in imported_order_ids]

    # Queryset lookup to get unique orders with unique source_id in the format: `order_id`-`source_id`
    source_id_lookup = Concat(
        'imported_order_tracks__order_id',
        Value('-'),
        'imported_order_tracks__source_id',
        output_field=CharField()
    )

    # Get already synced order sources
    order_source_ids = profit_search.annotate(
        order_source_id=source_id_lookup
    ).values_list('order_source_id', flat=True).distinct()

    # Search ShopifyOrderTrack for not synced order sources
    found_order_tracks = ShopifyOrderTrack.objects.filter(
        store_id=store_id,
        order_id__in=shopify_orders.values_list('order_id', flat=True),
        data__regex=r'.+?"aliexpress".+?"order_details".+?"cost".+?"total"'
    ).annotate(
        order_source_id=Concat('order_id', Value('-'), 'source_id', output_field=CharField())
    ).filter(
        ~Q(order_source_id__in=order_source_ids)
    )

    # Merge order_id from ShopifyOrder with ShopifyOrderTrack
    found_orders = list(set(found_orders + list(found_order_tracks.values_list('order_id', flat=True))))

    running_calculation = len(found_orders) > 0
    if running_calculation:
        cache_shopify_profits.apply_async(
            args=[
                store_id,
                found_orders,
                list(found_order_tracks.values_list('id', flat=True)),
                imported_order_ids,
                list(order_source_ids)
            ],
            countdown=5,  # Waiting for page to reload so cache doesn't finish first and no profits are sent
        )

    return running_calculation


def retrieve_current_profits(user_id, store_id, start, end):
    # meta = get_meta(start, end, current_page, limit)
    # base_start_date = meta['start']
    # base_end_date = meta['end']

    result = initialize_base_dict(start, end)

    facebook_data = get_facebook_profit(user_id, store_id, start, end)
    shopify_data = get_shopify_profit(store_id, start, end)

    profits, totals = merge_profits([facebook_data, shopify_data], result)
    totals['orders_per_day'] = totals['orders_count'] / (end - start).days

    return profits, totals
