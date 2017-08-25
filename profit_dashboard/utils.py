import arrow
from datetime import timedelta, date
from collections import OrderedDict
from math import ceil

from django.conf import settings
from django.db.models import Q
from django.utils.text import slugify
from facebookads.api import FacebookAdsApi
from facebookads.adobjects.user import User
from facebookads.adobjects.adaccount import AdAccount

from .models import (
    FacebookAccess,
    FacebookAccount,
    FacebookInsight,
    ShopifyProfit,
)
from .tasks import fetch_facebook_insights, cache_shopify_profits
from shopify_orders.models import ShopifyOrder


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
              'other_costs': 0.0, 'outcome': 0.0, 'profit': 0.0}

    for source in data:
        for date_key, items in source.items():
            revenue = float(items.get('revenue', 0.0))
            fulfillment_cost = float(items.get('fulfillment_cost', 0.0))
            ad_spend = float(items.get('ad_spend', 0.0))
            other_costs = float(items.get('other_costs', 0.0))

            totals['revenue'] += revenue
            totals['fulfillment_cost'] += fulfillment_cost
            totals['ad_spend'] += ad_spend
            totals['other_costs'] += other_costs

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
    return {
        profit.date.strftime('%m/%d/%Y'): {
            'revenue': profit.revenue,
            'fulfillment_cost': profit.fulfillment_cost,
            'other_costs': profit.other_costs,
        } for profit in ShopifyProfit.objects.filter(
            store_id=store_id,
            date__range=(start_date, end_date)
        )
    }


def get_facebook_profit(user_id, start_date, end_date):
    access = FacebookAccess.objects.filter(user_id=user_id)

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


def get_facebook_ads(user, access_token):
    access, created = FacebookAccess.objects.get_or_create(user=user, defaults={
        'access_token': access_token
    })

    if access_token != access.access_token:
        access.access_token = access_token
        access.save()

    api = FacebookAdsApi.init(
        settings.FACEBOOK_APP_ID,
        settings.FACEBOOK_APP_SECRET,
        access_token
    )

    user = User(fbid='me', api=api)
    accounts = list(user.get_ad_accounts(fields=[AdAccount.Field.name]))
    params = {'time_increment': 1}

    for account in accounts:
        account_model, created = FacebookAccount.objects.get_or_create(
            account_id=account.get(account.Field.id),
            access=access,
            defaults={
                'account_name': account.get(account.Field.name),
                'last_sync': date.today()
            }
        )

        if account_model is not None and account_model.last_sync:
            params['time_range'] = {
                'since': account_model.last_sync.strftime('%Y-%m-%d'),
                'until': date.today().strftime('%Y-%m-%d')
            }

        if not created:
            account_model.last_sync = date.today()
            account_model.save()

        insights = account.get_insights(params=params)
        for insight in list(insights):
            insight_object, created = FacebookInsight.objects.get_or_create(
                account=account_model,
                date=arrow.get(insight[insight.Field.date_start]).datetime,
                defaults={
                    'impressions': int(insight.get(insight.Field.impressions, '0')),
                    'spend': float(insight.get(insight.Field.spend, '0')),
                }
            )

            if not created:
                insight_object.impressions = int(insight.get(insight.Field.impressions, '0'))
                insight_object.spend = float(insight.get(insight.Field.spend, '0'))
                insight_object.save()


def retrieve_facebook_insights(user_id, store_id, access_token):
    fetch_facebook_insights.delay(user_id, store_id, access_token)


def calculate_shopify_profit(user_id, store_id, start_date, end_date):
    imported_order_ids = ShopifyProfit.objects.filter(
        store_id=store_id,
        date__range=(start_date, end_date)
    ).values_list('imported_orders__order_id', flat=True)
    found_orders = list(ShopifyOrder.objects.filter(
        ~Q(order_id__in=imported_order_ids),
        store_id=store_id,
        created_at__range=(start_date, end_date)
    ).values_list('id', flat=True))

    running_calculation = len(found_orders) > 1
    if running_calculation:
        cache_shopify_profits.delay(
            user_id,
            store_id,
            found_orders
        )

    return running_calculation


def retrieve_current_profits(user_id, store_id, start, end, current_page, limit=None, filter_date=None):
    meta = get_meta(start, end, current_page, limit)
    base_start_date = meta['start']
    base_end_date = meta['end']

    if filter_date is not None:
        base_start_date, base_end_date = filter_date

    result = initialize_base_dict(base_start_date, base_end_date)

    facebook_data = get_facebook_profit(user_id, start, end)
    shopify_data = get_shopify_profit(store_id, start, end)

    profits, totals = merge_profits([facebook_data, shopify_data], result)

    return profits, meta['max_results'], meta['pages'], totals
