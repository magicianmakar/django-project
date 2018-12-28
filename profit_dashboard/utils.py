import arrow
import pytz
import re
import simplejson as json

from datetime import date
from collections import OrderedDict

from django.db.models import Sum
from django.utils import timezone

from shopified_core.paginators import SimplePaginator
from shopify_orders.models import ShopifyOrder
from leadgalaxy.utils import safeFloat, get_shopify_orders
from leadgalaxy.models import ShopifyOrderTrack

from .models import (
    FacebookAccess,
    FacebookAdCost,
    AliexpressFulfillmentCost,
    OtherCost
)

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


def create_facebook_ads(facebook_account, campaign_insight):
    # Using update_or_create for updating insights returned on the same day of last_sync
    FacebookAdCost.objects.update_or_create(
        account=facebook_account,
        created_at=campaign_insight['created_at'],
        campaign_id=campaign_insight['campaign_id'],
        defaults={
            'impressions': campaign_insight['impressions'],
            'spend': campaign_insight['spend'],
        }
    )


def get_facebook_ads(facebook_access_id, store, verbosity=1):
    """ Get Insights from all accounts/campaigns selected from the facebook_access_id
    """
    facebook_access = FacebookAccess.objects.get(id=facebook_access_id, store=store)

    # Only selected accounts have a corresponding FacebookAccount model
    accounts = facebook_access.accounts.all()
    if verbosity > 1:
        print 'Sync {} Facebook AdAccount'.format(len(accounts))

    for account in accounts:
        if verbosity > 1:
            print '\tSync {} Facebook Campaigns'.format(len(account.campaigns.split(',')))

        # Return already formatted insights
        for insight in account.get_api_insights(verbosity=verbosity):
            create_facebook_ads(account, insight)

        account.last_sync = date.today()
        account.save()


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
            'fulfillments_count': 0,
            'orders_count': 0,
            'ad_spend': 0.0,
            'other_costs': 0.0,
            'outcome': 0.0,
            'profit': 0.0,
        }

    # Shopify Orders
    orders = ShopifyOrder.objects.filter(store_id=store_id,
                                         created_at__range=(start, end),
                                         financial_status__in=['authorized', 'partially_paid', 'paid', 'partially_refunded', 'refunded'])

    orders_map = {}
    totals_orders_count = 0
    for order in orders.values('created_at', 'total_price', 'order_id'):
        # Date: YYYY-MM-DD
        try:
            # Correct our database date to show these at the correct day
            created_at = arrow.get(order['created_at']).to(store_timezone)
        except:
            pass
        date_key = created_at.format('YYYY-MM-DD')
        if date_key not in profits_data:
            continue

        totals_orders_count += 1
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

        profits_data[date_key]['profit'] += order['total_price']
        profits_data[date_key]['revenue'] += order['total_price']
        profits_data[date_key]['orders_count'] += 1
        profits_data[date_key]['empty'] = False
        profits_data[date_key]['css_empty'] = ''

    # Account for refunds processed within date range
    refunds = []
    total_refunds = 0.0
    for refund in order_refunds(store, start, end, store_timezone):
        refunds.append(refund)

        date_key = arrow.get(refund['processed_at']).format('YYYY-MM-DD')
        if date_key not in profits_data:
            continue

        refund_amount = get_refund_amount(refund.get('transactions'))
        if refund_amount:
            total_refunds += refund_amount
            profits_data[date_key]['profit'] -= refund_amount
            profits_data[date_key]['revenue'] -= refund_amount
            profits_data[date_key]['empty'] = False
            profits_data[date_key]['css_empty'] = ''

    # Aliexpress costs
    shippings = AliexpressFulfillmentCost.objects.filter(store_id=store_id, order_id__in=orders.values('order_id'))

    total_fulfillments_count = 0
    for shipping in shippings:
        if shipping.order_id not in orders_map:
            continue

        date_key = orders_map.get(shipping.order_id, {}).get('date')
        date_key = arrow.get(date_key).format('YYYY-MM-DD')
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

    total_ad_costs = 0.0
    for ad_cost in ad_costs:
        date_key = arrow.get(ad_cost['date_key']).format('YYYY-MM-DD')
        if date_key not in profits_data:
            continue

        ad_cost_amount = safeFloat(ad_cost['spend__sum'])
        profits_data[date_key]['profit'] -= safeFloat(ad_cost['spend__sum'])
        profits_data[date_key]['ad_spend'] = ad_cost_amount
        profits_data[date_key]['empty'] = False
        profits_data[date_key]['css_empty'] = ''
        total_ad_costs += ad_cost_amount

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
        'ads_spend': total_ad_costs,
        'other_costs': other_costs.aggregate(total=Sum('amount__sum'))['total'] or 0.0,
        'average_profit': 0.0,
        'average_revenue': 0.0,
        'refunds': total_refunds,
    }
    totals['outcome'] = safeFloat(totals['fulfillment_cost']) + safeFloat(totals['ads_spend']) + safeFloat(totals['other_costs'])
    totals['profit'] = safeFloat(totals['revenue']) - safeFloat(totals['outcome']) - safeFloat(total_refunds)
    totals['orders_count'] = totals_orders_count
    totals['fulfillments_count'] = total_fulfillments_count
    totals['orders_per_day'] = totals['orders_count'] / len(days)
    totals['fulfillments_per_day'] = total_fulfillments_count / len(days)
    totals['profit_margin'] = calculate_profit_margin(totals['revenue'], totals['profit'])
    if totals['orders_count'] != 0:
        totals['average_profit'] = totals['profit'] / totals['orders_count']
        totals['average_revenue'] = totals['revenue'] / totals['orders_count']

    details = get_profit_details(store,
                                 (start, end),
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
    params = {
        'updated_at_min': arrow.get(start).isoformat(),
        'updated_at_max': arrow.get(end).isoformat(),
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
                    # Correct our database date to show these at the correct day
                    processed_at = arrow.get(refund.get('processed_at')).to(store_timezone)
                    # Only yield refunds processed within date range
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
    start, end = date_range

    if not orders_map:
        orders_map = {}
        orders = ShopifyOrder.objects.filter(
            store_id=store.id,
            created_at__range=date_range,
            financial_status__in=['authorized', 'partially_paid', 'paid', 'partially_refunded', 'refunded']
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
        refunds_list = order_refunds(store, start, end, store_timezone)

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


def get_date_range(request, store_timezone):
    end = arrow.now()
    start = arrow.now().replace(days=-30)
    date_range = request.GET.get('date_range', '{}-{}'.format(start.format('MM/DD/YYYY'), end.format('MM/DD/YYYY')))

    if date_range:
        try:
            daterange_list = date_range.split('-')
            # Get timezone from user store, if it doesn't exist, we save it the first time they access PD
            tz = timezone.now().astimezone(pytz.timezone(store_timezone)).strftime(' %z')

            start = arrow.get(daterange_list[0] + tz, r'MM/DD/YYYY Z')

            if len(daterange_list) > 1 and daterange_list[1]:
                end = arrow.get(daterange_list[1] + tz, r'MM/DD/YYYY Z')
                end = end.span('day')[1]
            else:
                end = arrow.now()

        except:
            pass

    return start.datetime, end.datetime
