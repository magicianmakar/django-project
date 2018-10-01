import arrow
import re
import simplejson as json

from datetime import date
from collections import OrderedDict

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from facebookads.api import FacebookAdsApi
from facebookads.adobjects.user import User as FBUser
from facebookads.adobjects.adaccount import AdAccount

from shopified_core.paginators import SimplePaginator
from shopify_orders.models import ShopifyOrder
from leadgalaxy.utils import safeFloat, get_shopify_orders
from leadgalaxy.models import ShopifyOrderTrack

from .models import (
    FacebookAccess,
    FacebookAccount,
    FacebookAdCost,
    AliexpressFulfillmentCost,
    OtherCost
)

INITIAL_DATE = arrow.get('2018-06-01')

ALIEXPRESS_CANCELLED_STATUS = [
    'buyer_pay_timeout',
    'risk_reject_closed',
    # 'buyer_accept_goods_timeout',
    'buyer_cancel_notpay_order',
    'cancel_order_close_trade',
    'seller_send_goods_timeout',
    'buyer_cancel_order_in_risk',
    # 'buyer_accept_goods',
    'seller_accept_issue_no_goods_return',
    'seller_response_issue_timeout',
]


def get_facebook_api(access_token):
    return FacebookAdsApi.init(
        settings.FACEBOOK_APP_ID,
        settings.FACEBOOK_APP_SECRET,
        access_token,
        api_version='v3.0'
    )


def get_facebook_ads(facebook_access_id, store):
    access = FacebookAccess.objects.get(id=facebook_access_id, store=store)
    access_token = access.get_or_update_token()

    api = get_facebook_api(access_token)
    user = FBUser(fbid='me', api=api)

    params = {'time_increment': 1}

    account_ids = access.account_ids.split(',')
    accounts = user.get_ad_accounts(fields=[AdAccount.Field.name])
    for account in accounts:
        if account['id'] not in account_ids:
            continue

        try:
            account_model = FacebookAccount.objects.get(
                account_id=account.get(account.Field.id),
                access=access,
                store=store
            )
        except FacebookAccount.DoesNotExist:
            continue

        if account_model.last_sync:
            params['time_range'] = {
                'since': arrow.get(account_model.last_sync).replace(days=-1).format('YYYY-MM-DD'),
                'until': date.today().strftime('%Y-%m-%d')
            }

        campaigns = account_model.campaigns.split(',')
        campaign_insights = {}
        for campaign in account.get_campaigns(fields=['name', 'status', 'created_time']):
            if 'include' in account_model.config and campaign['id'] not in campaigns:
                campaign_date = arrow.get(campaign['created_time']).datetime
                if 'new' in account_model.config and campaign_date > account_model.updated_at:
                    campaigns.append(campaign['id'])
                else:
                    continue
            if 'exclude' in account_model.config and campaign['id'] in campaigns:
                continue

            for insight in campaign.get_insights(params=params):
                insight_date = arrow.get(insight[insight.Field.date_start]).format('YYYY-MM-DD')
                insight_key = '{}-{}'.format(insight_date, campaign['id'])
                if insight_key not in campaign_insights:
                    campaign_insights[insight_key] = {
                        'impressions': int(insight[insight.Field.impressions]),
                        'spend': float(insight[insight.Field.spend]),
                        'created_at': arrow.get(insight[insight.Field.date_start]).date(),
                        'campaign_id': campaign['id'],
                    }
                else:
                    campaign_insights[insight_key]['impressions'] += int(insight[insight.Field.impressions])
                    campaign_insights[insight_key]['spend'] += float(insight[insight.Field.spend])

        for key, value in campaign_insights.items():
            FacebookAdCost.objects.update_or_create(
                account=account_model,
                created_at=value['created_at'],
                campaign_id=value['campaign_id'],
                defaults={
                    'impressions': value['impressions'],
                    'spend': value['spend'],
                }
            )

        account_model.campaigns = ','.join(campaigns)
        account_model.last_sync = date.today()
        account_model.save()


def calculate_profit_margin(revenue, profit):
    if revenue < profit or revenue == 0 or profit < 0:
        percentage = 0
    else:
        percentage = profit / revenue * 100
    return '{}%'.format(int(percentage))


def calculate_profits(profits):
    for profit in profits:
        profit['outcome'] = profit['fulfillment_cost'] + profit['ad_spend'] + profit['other_costs']
        profit['profit'] = profit['revenue'] - profit['outcome']
        profit['return_over_investment'] = calculate_profit_margin(profit['revenue'], profit['profit'])

    return profits


def get_profits(store, start, end, store_timezone=''):
    store_id = store.id
    days = arrow.Arrow.range('day', start, end) + [arrow.get(end)]
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
            'fulfillments_count': 0,
            'orders_count': 0,
            'ad_spend': 0.0,
            'other_costs': 0.0,
            'outcome': 0.0,
            'profit': 0.0,
        }

    # Shopify Orders
    orders = ShopifyOrder.objects.filter(store_id=store_id,
                                         created_at__range=(start, end))

    orders_map = {}
    for order in orders.values('created_at', 'total_price', 'order_id'):
        # Date: YYYY-MM-DD
        try:
            created_at = arrow.get(order['created_at']).to(store_timezone)
        except:
            pass
        date_key = created_at.format('YYYY-MM-DD')
        orders_map[order['order_id']] = {
            'date': created_at.datetime,
            'date_as_string': created_at.format('MM/DD/YYYY'),
            'order_id': order['order_id'],
            'total_price': order['total_price'],
            'total_refund': 0.0,
            'profit': order['total_price'],
            'products': [],
            'refunded_products': [],
            'aliexpress_track': []
        }
        if date_key not in profits_data:
            continue

        profits_data[date_key]['profit'] += order['total_price']
        profits_data[date_key]['revenue'] += order['total_price']
        profits_data[date_key]['orders_count'] += 1
        profits_data[date_key]['empty'] = False
        profits_data[date_key]['css_empty'] = ''

    # Account for refunds processed within date range
    refunds = []
    for refund in order_refunds(store, start, end, store_timezone):
        refunds.append(refund)

        date_key = arrow.get(refund['processed_at']).format('YYYY-MM-DD')
        if date_key not in profits_data:
            continue

        refund_amount = get_refund_amount(refund.get('transactions'))
        if refund_amount:
            profits_data[date_key]['profit'] -= refund_amount
            profits_data[date_key]['revenue'] -= refund_amount
            profits_data[date_key]['empty'] = False
            profits_data[date_key]['css_empty'] = ''

    # Aliexpress costs
    shippings = AliexpressFulfillmentCost.objects.filter(store_id=store_id,
                                                         order_id__in=orders_map.keys())

    total_fulfillments_count = 0
    for shipping in shippings:
        date_key = arrow.get(orders_map[shipping.order_id]['date']).format('YYYY-MM-DD')
        if date_key not in profits_data:
            continue

        profits_data[date_key]['profit'] -= safeFloat(shipping.total_cost)
        profits_data[date_key]['fulfillment_cost'] += safeFloat(shipping.total_cost)
        profits_data[date_key]['fulfillments_count'] += 1
        total_fulfillments_count += 1
        profits_data[date_key]['empty'] = False
        profits_data[date_key]['css_empty'] = ''

    # Facebook Insights
    ad_costs = FacebookAdCost.objects.filter(account__access__store_id=store_id,
                                             created_at__range=(start, end)) \
                                     .extra({'date_key': 'date(created_at)'}) \
                                     .values('date_key') \
                                     .annotate(Sum('spend')) \
                                     .order_by('date_key')

    for ad_cost in ad_costs:
        date_key = arrow.get(ad_cost['date_key']).format('YYYY-MM-DD')
        if date_key not in profits_data:
            continue

        profits_data[date_key]['profit'] -= safeFloat(ad_cost['spend__sum'])
        profits_data[date_key]['ad_spend'] = safeFloat(ad_cost['spend__sum'])
        profits_data[date_key]['empty'] = False
        profits_data[date_key]['css_empty'] = ''

    # Other Costs
    other_costs = OtherCost.objects.filter(store_id=store_id,
                                           date__range=(start, end)) \
                                   .extra({'date_key': 'date(date)'}) \
                                   .values('date_key') \
                                   .annotate(Sum('amount')) \
                                   .order_by('date_key')

    for other_cost in other_costs:
        date_key = arrow.get(other_cost['date_key']).format('YYYY-MM-DD')
        if date_key not in profits_data:
            continue

        other_cost_value = safeFloat(other_cost['amount__sum'])
        is_empty = profits_data[date_key]['empty']

        profits_data[date_key]['profit'] -= other_cost_value
        profits_data[date_key]['other_costs'] = other_cost_value
        # Other costs might be saved as 0
        profits_data[date_key]['empty'] = is_empty and other_cost_value == 0
        profits_data[date_key]['css_empty'] = ''

    # Totals
    totals = {
        'revenue': orders.aggregate(total=Sum('total_price'))['total'] or 0.0,
        'fulfillment_cost': shippings.aggregate(total=Sum('total_cost'))['total'] or 0.0,
        'ads_spend': ad_costs.aggregate(total=Sum('spend__sum'))['total'] or 0.0,
        'other_costs': other_costs.aggregate(total=Sum('amount__sum'))['total'] or 0.0,
        'average_profit': 0.0,
        'average_revenue': 0.0,
    }
    totals['outcome'] = safeFloat(totals['fulfillment_cost']) + safeFloat(totals['ads_spend']) + safeFloat(totals['other_costs'])
    totals['profit'] = safeFloat(totals['revenue']) - safeFloat(totals['outcome'])
    totals['orders_count'] = ShopifyOrder.objects.filter(store_id=store_id, created_at__range=(start, end)).count()
    totals['fulfillments_count'] = total_fulfillments_count
    totals['orders_per_day'] = totals['orders_count'] / len(days)
    totals['fulfillments_per_day'] = total_fulfillments_count / len(days)
    totals['profit_margin'] = calculate_profit_margin(totals['revenue'], totals['profit'])
    if totals['orders_count'] != 0:
        totals['average_profit'] = totals['profit'] / totals['orders_count']
        totals['average_revenue'] = totals['revenue'] / totals['orders_count']

    # Details
    try:
        date_range = (arrow.get(start).to(store_timezone).datetime,
                      arrow.get(end).to(store_timezone).datetime)
    except:
        date_range = (start, end)
    details = get_profit_details(store,
                                 date_range,
                                 limit=20,
                                 page=1,
                                 orders_map=orders_map,
                                 refunds_list=refunds,
                                 store_timezone=store_timezone)

    return profits_data.values(), totals, details


def get_costs_from_track(track, commit=False):
    """Get Aliexpress cost data from Order Track and (optionally) commit changes to the database

    Args:
        track (ShopifyOrderTrack): Order Track
        commit (bool, optional): Commit changes to the database:
            - Update or create AliexpressFulfillmentCost from the track data
            - Remove AliexpressFulfillmentCost is the order is canceled in Aliexpress

    Returns:
        (dict/None): Return None in case of error or track doesn't have costs
    """

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

        cost = data['aliexpress']['order_details']['cost']
        if type(cost.get('total')) in [float, int, long]:
            costs['total_cost'] = cost.get('total')
            costs['shipping_cost'] = cost.get('shipping')
            costs['products_cost'] = cost.get('products')
        else:
            costs['total_cost'] = cost.get('total').replace(',', '.')
            costs['shipping_cost'] = cost.get('shipping').replace(',', '.')
            costs['products_cost'] = cost.get('products').replace(',', '.')

        if data['aliexpress']['end_reason'] and data['aliexpress']['end_reason'].lower() in ALIEXPRESS_CANCELLED_STATUS:
            # Remove cancelled fulfillment costs
            if commit:
                AliexpressFulfillmentCost.objects.filter(
                    store=track.store,
                    order_id=track.order_id,
                    source_id=track.source_id
                ).delete()
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
            while True:
                try:
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

                except AliexpressFulfillmentCost.MultipleObjectsReturned:
                    AliexpressFulfillmentCost.objects.filter(
                        store=track.store,
                        order_id=track.order_id,
                        source_id=track.source_id,
                    ).delete()

                    continue

                break

        return costs


def order_refunds(store, start, end, store_timezone=''):
    try:
        params = {
            'updated_at_min': arrow.get(start).to(store_timezone).isoformat(),
            'updated_at_max': arrow.get(end).to(store_timezone).isoformat(),
        }
    except:
        params = {
            'updated_at_min': start.isoformat(),
            'updated_at_max': end.isoformat(),
        }

    def retrieve_refunds(params):
        orders_count = 250
        limit = 250
        page = 1
        while orders_count >= limit:
            shopify_orders = get_shopify_orders(store, page=page, limit=limit, fields='refunds', extra_params=params, raise_for_status=True)
            orders_count = 0
            for order in shopify_orders:
                orders_count += 1
                for refund in order.get('refunds'):
                    # Only yield refunds processed within date range
                    processed_at = arrow.get(refund.get('processed_at'))
                    if start < processed_at < end:
                        refund['processed_at_datetime'] = processed_at
                        yield refund

            # There is still another page while orders count is at its max limit
            page += 1

    # Partially refunded
    params['financial_status'] = 'partially_refunded'
    for refund in retrieve_refunds(params):
        yield refund

    # Refunded and partially refunded can only be retrieved separately
    params['financial_status'] = 'refunded'
    for refund in retrieve_refunds(params):
        yield refund


def get_refund_amount(transactions):
    refund_amount = 0.0
    for transaction in transactions:
        kind = transaction.get('kind', 'refund')
        test_transaction = transaction.get('test', False)
        if not test_transaction and kind == 'refund':
            refund_amount += float(transaction.get('amount'))

    return refund_amount


def get_profit_details(store, date_range, limit=20, page=1, orders_map={}, refunds_list=[], store_timezone=''):
    """
    Returns each refund, order and aliexpress fulfillment sorted by date
    """
    if not orders_map:
        orders_map = {}
        orders = ShopifyOrder.objects.filter(
            store_id=store.id,
            created_at__range=date_range
        ).values('created_at', 'total_price', 'order_id')
        for order in orders:
            created_at = arrow.get(order['created_at'])
            try:
                created_at = created_at.to(store_timezone)
            except:
                pass

            orders_map[order['order_id']] = {
                'date': created_at.datetime,
                'date_as_string': created_at.format('MM/DD/YYYY'),
                'order_id': order['order_id'],
                'total_price': order['total_price'],
                'total_refund': 0.0,
                'profit': order['total_price'],
                'products': [],
                'refunded_products': [],
                'aliexpress_track': []
            }

    if not refunds_list:
        refunds_list = order_refunds(store, date_range[0], date_range[1], store_timezone)

    # Merge refunds with orders
    new_refunds = {}  # For refunds done later than order.created_at
    for refund in refunds_list:
        order_id = refund.get('order_id')
        processed_at = refund['processed_at_datetime']
        order_created_at = orders_map.get(order_id, {}).get('date')

        # Sum refund amount
        refund_amount = get_refund_amount(refund.get('transactions'))

        # Refunded products
        refunded_products = [i.get('line_item') for i in refund.get('refund_line_items', [])]

        # Same refund.processed_at as order.created_at shows at the same row
        if order_created_at and order_created_at.date() == processed_at.date():
            orders_map[order_id]['total_refund'] -= refund_amount
            orders_map[order_id]['profit'] -= refund_amount
            orders_map[order_id]['refunded_products'] += refunded_products
        else:
            refunds_key = '{}-{}'.format(processed_at.format('YYYY-MM-DD'), order_id)
            if refunds_key not in new_refunds:
                new_refunds[refunds_key] = {
                    'date': processed_at.datetime,
                    'date_as_string': processed_at.format('MM/DD/YYYY'),
                    'order_id': refund.get('order_id'),
                    'profit': 0.0,
                    'total_refund': 0.0,
                    'refunded_products': [],
                }

            new_refunds[refunds_key]['profit'] -= refund_amount
            new_refunds[refunds_key]['total_refund'] -= refund_amount
            new_refunds[refunds_key]['refunded_products'] += refunded_products

    # Paginate profit details
    profit_details = orders_map.values() + new_refunds.values()
    profit_details = sorted(profit_details, key=lambda k: k['date'], reverse=True)
    paginator = SimplePaginator(profit_details, limit)
    page = min(max(1, page), paginator.num_pages)
    profit_details = paginator.page(page)

    # Get track for orders being shown
    order_ids = [i.get('order_id') for i in profit_details]
    tracks_map = {}
    existing_order_tracks = []
    for track in ShopifyOrderTrack.objects.filter(store=store, order_id__in=order_ids):
        # We only need distinct track's
        key = '{}-{}'.format(track.order_id, track.source_id)
        if key in existing_order_tracks:
            continue

        existing_order_tracks.append(key)

        costs = get_costs_from_track(track)
        if costs:
            if track.order_id not in tracks_map:
                tracks_map[track.order_id] = []

            tracks_map[track.order_id].append({
                'source_id': track.source_id,
                'source_url': track.get_source_url(),
                'costs': costs
            })

    def sum_costs(x, y):
        return x + float(y['costs']['total_cost'])

    shopify_orders = get_shopify_orders(store, page=1, limit=limit, fields='name,id,line_items', order_ids=order_ids, raise_for_status=True)
    shopify_orders = {
        i['id']: {
            'name': i['name'],
            'line_items': i.get('line_items', [])
        }
        for i in shopify_orders
    }

    # Merge tracks with orders
    for detail in profit_details:
        order_id = detail.get('order_id')
        shopify_order = shopify_orders.get(order_id, {})
        row_with_order = 'total_price' in detail

        if row_with_order:  # Only get tracks and line items if not just a refund
            detail['products'] = shopify_order.get('line_items', [])

            order_tracks = tracks_map.get(order_id, [])
            fulfillment_cost = reduce(sum_costs, order_tracks, 0)

            if fulfillment_cost:
                detail['aliexpress_tracks'] = order_tracks
                detail['profit'] -= fulfillment_cost
                detail['fulfillment_cost'] = fulfillment_cost

        detail['shopify_url'] = store.get_link('/admin/orders/{}'.format(order_id))
        detail['order_name'] = shopify_order.get('name')

    return profit_details, paginator


def get_date_range(request):
    start = request.GET.get('start')
    end = request.GET.get('end')
    tz = timezone.localtime(timezone.now()).strftime(' %z')
    if end is None:
        end = arrow.now()
    else:
        end = arrow.get(end + tz, r'MM/DD/YYYY Z')

    if start is None:
        start = arrow.now().replace(days=-30)
    else:
        start = arrow.get(start + tz, r'MM/DD/YYYY Z')

    try:
        end = end.to(request.session['django_timezone']).datetime
        start = start.to(request.session['django_timezone']).datetime
    except:
        end = end.datetime
        start = start.datetime

    return start, end
