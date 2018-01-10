import arrow
import re
import simplejson as json

from datetime import date
from collections import OrderedDict

from django.conf import settings
from django.db.models import Sum

from facebookads.api import FacebookAdsApi
from facebookads.adobjects.user import User as FBUser
from facebookads.adobjects.adaccount import AdAccount

from shopify_orders.models import ShopifyOrder
from leadgalaxy.utils import safeFloat

from .models import (
    FacebookAccess,
    FacebookAccount,
    FacebookAdCost,
    AliexpressFulfillmentCost,
    OtherCost
)


def get_facebook_ads(user, store, access_token=None, account_ids=None, campaigns=None, config='include'):
    access, created = FacebookAccess.objects.update_or_create(user=user, store=store, defaults={
        'access_token': access_token,
        'account_ids': ','.join(account_ids) if account_ids else '',
        'campaigns': ','.join(campaigns) if campaigns else ''
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
        access_token,
        api_version='v2.10'
    )

    user = FBUser(fbid='me', api=api)
    accounts = user.get_ad_accounts(fields=[AdAccount.Field.name])
    params = {'time_increment': 1}

    for account in accounts:
        if account['id'] not in account_ids:
            continue

        account_model, created = FacebookAccount.objects.update_or_create(
            account_id=account.get(account.Field.id),
            access=access,
            store=store,
            defaults={
                'account_name': account.get(account.Field.name),
                'last_sync': date.today(),
                'config': config
            }
        )

        if account_model.last_sync:
            params['time_range'] = {
                'since': account_model.last_sync.strftime('%Y-%m-%d'),
                'until': date.today().strftime('%Y-%m-%d')
            }

        campaign_insights = {}
        for campaign in account.get_campaigns(fields=['name', 'status', 'created_time']):
            if 'include' in config and campaign['id'] not in campaigns:
                continue
            if 'exclude' in config and campaign['id'] in campaigns:
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
            FacebookAdCost.objects.update_or_create(account=account_model, created_at=key, defaults=val)

        account_model.last_sync = date.today()
        account_model.save()


def get_profits(user_id, store_id, start, end):
    days = arrow.Arrow.range('day', start, end)
    profits_data = OrderedDict()
    for day in reversed(days):
        date_key = day.format('YYYY-MM-DD')
        profits_data[date_key] = {
            'date_as_string': day.format('MM/DD/YYYY'),
            'date_as_slug': date_key,
            'week_day': day.strftime('%A'),
            'empty': True,
            'css_empty': 'empty',
            'revenue': 0.0,
            'fulfillment_cost': 0.0,
            'ad_spend': 0.0,
            'other_costs': 0.0,
            'outcome': 0.0,
            'profit': 0.0
        }

    orders = ShopifyOrder.objects.filter(store_id=store_id, created_at__range=(start, end)) \
                                 .extra({'date_key': 'date(created_at)'}) \
                                 .values('date_key') \
                                 .annotate(Sum('total_price')) \
                                 .order_by('date_key')

    for order in orders:
        # Date: YYYY-MM-DD
        date_key = arrow.get(order['date_key']).format('YYYY-MM-DD')
        profits_data[date_key]['revenue'] = order['total_price__sum']
        profits_data[date_key]['empty'] = False
        profits_data[date_key]['css_empty'] = ''

    shippings = AliexpressFulfillmentCost.objects.filter(store_id=store_id, created_at__range=(start, end)) \
                                                 .extra({'date_key': 'date(created_at)'}) \
                                                 .values('date_key') \
                                                 .annotate(Sum('shipping_cost'),
                                                           Sum('products_cost'),
                                                           Sum('total_cost')) \
                                                 .order_by('date_key')

    for shipping in shippings:
        date_key = arrow.get(shipping['date_key']).format('YYYY-MM-DD')
        profits_data[date_key]['fulfillment_cost'] = safeFloat(shipping['total_cost__sum'])
        profits_data[date_key]['empty'] = False
        profits_data[date_key]['css_empty'] = ''

    ad_costs = FacebookAdCost.objects.filter(account__access__store_id=store_id,
                                             account__access__user_id=user_id,
                                             created_at__range=(start, end)) \
                                     .extra({'date_key': 'date(created_at)'}) \
                                     .values('date_key') \
                                     .annotate(Sum('spend')) \
                                     .order_by('date_key')

    for ad_cost in ad_costs:
        date_key = arrow.get(ad_cost['date_key']).format('YYYY-MM-DD')
        profits_data[date_key]['ad_spend'] = safeFloat(ad_cost['spend__sum'])
        profits_data[date_key]['empty'] = False
        profits_data[date_key]['css_empty'] = ''

    other_costs = OtherCost.objects.filter(store_id=store_id) \
                                   .extra({'date_key': 'date(date)'}) \
                                   .values('date_key') \
                                   .annotate(Sum('amount')) \
                                   .order_by('date_key')

    for other_cost in other_costs:
        date_key = arrow.get(other_cost['date_key']).format('YYYY-MM-DD')
        profits_data[date_key]['other_costs'] = safeFloat(other_cost['amount__sum'])
        profits_data[date_key]['empty'] = False
        profits_data[date_key]['css_empty'] = ''

    totals = {
        'revenue': orders.aggregate(total=Sum('total_price__sum'))['total'] or 0.0,
        'fulfillment_cost': shippings.aggregate(total=Sum('total_cost__sum'))['total'] or 0.0,
        'ad_spend': ad_costs.aggregate(total=Sum('spend__sum'))['total'] or 0.0,
        'other_costs': other_costs.aggregate(total=Sum('amount__sum'))['total'] or 0.0,
    }
    totals['outcome'] = safeFloat(totals['fulfillment_cost']) + safeFloat(totals['ad_spend']) + safeFloat(totals['other_costs'])
    totals['profit'] = safeFloat(totals['revenue']) - safeFloat(totals['outcome'])
    totals['orders_count'] = ShopifyOrder.objects.filter(store_id=store_id, created_at__range=(start, end)).count()
    totals['orders_per_day'] = totals['orders_count'] / len(days)

    return profits_data.values(), totals


def calculate_profits(profits):
    for profit in profits:
        profit['outcome'] = profit['fulfillment_cost'] + profit['ad_spend'] + profit['other_costs']
        profit['profit'] = profit['revenue'] - profit['outcome']

        if profit['revenue'] == 0 or profit['revenue'] < profit['profit'] or profit['profit'] < 0:
            percentage = 0
        else:
            percentage = profit['profit'] / profit['revenue'] * 100
        profit['return_over_investment'] = '{}%'.format(int(percentage))

    return profits


def get_costs_from_track(track, commit=False):
    """Get Aliexpress cost data from Order Track

    Args:
        track (ShopifyOrderTrack): Order Track
        commit (bool, optional): Update or create AliexpressFulfillmentCost from the track data

    Returns:
        (dict/None): Return None in case of error or track doesn't have costs
    """

    rejected_status = [
        'buyer_pay_timeout', 'risk_reject_closed', 'buyer_cancel_notpay_order', 'cancel_order_close_trade', 'seller_send_goods_timeout',
        'buyer_cancel_order_in_risk', 'buyer_accept_goods', 'seller_accept_issue_no_goods_return', 'seller_response_issue_timeout'
    ]

    costs = {
        'total_cost': 0.0,
        'shipping_cost': 0.0,
        'products_cost': 0.0,
    }

    try:
        data = json.loads(track.data.encode('utf-8')) if track.data else {}
    except:
        return

    if data.get('aliexpress') and data.get('aliexpress').get('order_details') and \
            data.get('aliexpress').get('order_details').get('cost'):
        costs['total_cost'] = data['aliexpress']['order_details']['cost'].get('total').replace(',', '.')
        costs['shipping_cost'] = data['aliexpress']['order_details']['cost'].get('shipping').replace(',', '.')
        costs['products_cost'] = data['aliexpress']['order_details']['cost'].get('products').replace(',', '.')

        if data['aliexpress']['end_reason'] and data['aliexpress']['end_reason'].lower() in rejected_status:
            return

        try:
            float(costs['total_cost']) + float(costs['shipping_cost']) + float(costs['products_cost'])
        except:
            costs['total_cost'] = re.sub(r'\.([0-9]{3})', r'\1', costs['total_cost'])
            costs['shipping_cost'] = re.sub(r'\.([0-9]{3})', r'\1', costs['shipping_cost'])
            costs['products_cost'] = re.sub(r'\.([0-9]{3})', r'\1', costs['products_cost'])

        try:
            float(costs['total_cost']) + float(costs['shipping_cost']) + float(costs['products_cost'])
        except:
            return

    if any(costs.values()):
        if commit:
            AliexpressFulfillmentCost.objects.update_or_create(
                store=track.store,
                order_id=track.order_id,
                source_id=track.source_id,
                defaults={
                    'created_at': track.created_at.date(),
                    'shipping_cost': costs['shipping_cost'],
                    'products_cost': costs['products_cost'],
                    'total_cost': costs['total_cost'],
                }
            )

        return costs
