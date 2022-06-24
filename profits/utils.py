import arrow
import json
import pytz
import re
from collections import OrderedDict
from decimal import Decimal
from functools import reduce

from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum
from django.utils import timezone

from bigcommerce_core import utils as bigcommerce_utils
from bigcommerce_core.models import BigCommerceOrderTrack
from commercehq_core import utils as chq_utils
from commercehq_core.models import CommerceHQOrderTrack
from ebay_core import utils as ebay_utils
from ebay_core.models import EbayOrderTrack
from facebook_core import utils as fb_utils
from google_core import utils as google_utils
from facebook_core.models import FBOrderTrack
from google_core.models import GoogleOrderTrack
from gearbubble_core import utils as gear_utils
from groovekart_core import utils as gkart_utils
from groovekart_core.models import GrooveKartOrderTrack
from leadgalaxy import utils as shopify_utils
from shopified_core.paginators import SimplePaginator
from shopified_core.utils import safe_float
from woocommerce_core import utils as woo_utils
from woocommerce_core.models import WooOrderTrack

from . import models

# Note: Ignore this status: buyer_accept_goods_timeout, buyer_accept_goods
ALIEXPRESS_CANCELLED_STATUS = [
    'buyer_pay_timeout',
    'risk_reject_closed',
    'buyer_cancel_notpay_order',
    'cancel_order_close_trade',
    'seller_send_goods_timeout',
    'buyer_cancel_order_in_risk',
    'seller_accept_issue_no_goods_return',
    'seller_response_issue_timeout',
]


def get_stores(user, store_type):
    if store_type == 'shopify':
        return user.profile.get_shopify_stores()
    elif store_type == 'gkart':
        return user.profile.get_gkart_stores()
    elif store_type == 'bigcommerce':
        return user.profile.get_bigcommerce_stores()
    elif store_type == 'woo':
        return user.profile.get_woo_stores()
    elif store_type == 'ebay':
        return user.profile.get_ebay_stores()
    elif store_type == 'fb':
        return user.profile.get_fb_stores()
    elif store_type == 'google':
        return user.profile.get_google_stores()
    elif store_type == 'chq':
        return user.profile.get_chq_stores()
    else:
        raise NotImplementedError('Store Type')


def get_store_from_request(request, store_type=''):
    store_id = request.POST.get('store') or request.GET.get('store')
    if store_id:
        return get_stores(request.user, store_type).get(id=store_id)

    if store_type == 'shopify':
        return shopify_utils.get_store_from_request(request)
    elif store_type == 'chq':
        return chq_utils.get_store_from_request(request)
    elif store_type == 'ebay':
        return ebay_utils.get_store_from_request(request)
    elif store_type == 'fb':
        return fb_utils.get_store_from_request(request)
    elif store_type == 'google':
        return google_utils.get_store_from_request(request)
    elif store_type == 'woo':
        return woo_utils.get_store_from_request(request)
    elif store_type == 'gear':
        return gear_utils.get_store_from_request(request)
    elif store_type == 'gkart':
        return gkart_utils.get_store_from_request(request)
    elif store_type == 'bigcommerce':
        return bigcommerce_utils.get_store_from_request(request)
    else:
        raise NotImplementedError('Store Type')


def get_store_order_track(store_type):
    if store_type == 'gkart':
        return GrooveKartOrderTrack
    elif store_type == 'bigcommerce':
        return BigCommerceOrderTrack
    elif store_type == 'ebay':
        return EbayOrderTrack
    elif store_type == 'fb':
        return FBOrderTrack
    elif store_type == 'google':
        return GoogleOrderTrack
    elif store_type == 'woo':
        return WooOrderTrack
    elif store_type == 'chq':
        return CommerceHQOrderTrack
    else:
        raise NotImplementedError('Store Type')


def get_date_range(request, user_timezone):
    end = arrow.now()
    start = arrow.now().replace(days=-30)
    date_range = request.GET.get('date_range', '{}-{}'.format(start.format('MM/DD/YYYY'), end.format('MM/DD/YYYY')))

    if date_range:
        try:
            daterange_list = date_range.split('-')
            # Get timezone from user store, if it doesn't exist, we save it the first time they access PD
            if user_timezone:
                tz = timezone.now().astimezone(pytz.timezone(user_timezone)).strftime(' %z')
            else:
                tz = timezone.now().strftime(' %z')

            start = arrow.get(daterange_list[0] + tz, r'MM/DD/YYYY Z')

            if len(daterange_list) > 1 and daterange_list[1]:
                end = arrow.get(daterange_list[1] + tz, r'MM/DD/YYYY Z')
                end = end.span('day')[1]
            else:
                end = arrow.now()

        except:
            pass

    return start.datetime, end.datetime


def calculate_profit_margin(revenue, profit):
    if revenue < profit or revenue == 0 or profit < 0:
        percentage = 0
    else:
        percentage = profit / float(revenue) * 100
    return '{}%'.format(int(percentage))


def calculate_profits(profits):
    for profit in profits:
        profit['outcome'] = profit['fulfillment_cost'] + profit['ad_spend'] + profit['other_costs']
        profit['profit'] = profit['revenue'] - profit['outcome']
        profit['return_over_investment'] = calculate_profit_margin(profit['revenue'], profit['profit'])

    return profits


def get_order_mappings(order, user_timezone):
    order_date = arrow.get(order.date)
    try:
        # Correct our database date to show these at the correct day
        order_date = order_date.to(user_timezone)
    except:
        pass

    if hasattr(order, 'store') and order.store.store_type == 'fb':
        products = [item.get('title') for item in order.items]
        return {
            'date': order_date.datetime,
            'date_as_string': order_date.format('MM/DD/YYYY'),
            'order_id': order.order_id,
            'fb_order_id': order.fb_order_id,
            'fb_order_url': order.order_url,
            'total_price': float(order.amount),
            'total_refund': 0.0,
            'profit': float(order.amount),
            'products': products,
            'refunded_products': [],
            'aliexpress_track': [],
            'order_name': order.order_name
        }

    return {
        'date': order_date.datetime,
        'date_as_string': order_date.format('MM/DD/YYYY'),
        'order_id': order.order_id,
        'total_price': float(order.amount),
        'total_refund': 0.0,
        'profit': float(order.amount),
        'products': order.get_items_dict(),
        'refunded_products': [],
        'aliexpress_track': [],
        'order_name': order.order_name
    }


def get_costs_from_track(track, commit=False):
    """Get Aliexpress cost data from Order Track and (optionally) commit changes to the database

    Args:
        track (OrderTrack): Order Track
        commit (bool, optional): Commit changes to the database:
            - Update or create FulfillmentCost from the track data
            - Remove FulfillmentCost is the order is canceled in Aliexpress/eBay

    Returns:
        (dict/None): Return None in case of error or track doesn't have costs
    """

    costs = {
        'total_cost': 0.0,
        'shipping_cost': 0.0,
        'products_cost': 0.0,
    }

    try:
        data = json.loads(track.data) if track.data else {}
    except:
        return

    if commit:
        store_content_type = ContentType.objects.get_for_model(track.store)

    if data.get('aliexpress') and data.get('aliexpress').get('order_details') and \
            data.get('aliexpress').get('order_details').get('cost'):

        cost = data['aliexpress']['order_details']['cost']
        if type(cost.get('total')) in [float, int]:
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
                models.FulfillmentCost.objects.filter(
                    store_content_type=store_content_type,
                    store_object_id=track.store.id,
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
                    models.FulfillmentCost.objects.update_or_create(
                        store_content_type=store_content_type,
                        store_object_id=track.store.id,
                        order_id=track.order_id,
                        source_id=track.source_id,
                        defaults={
                            'created_at': track.created_at.date(),
                            'shipping_cost': costs['shipping_cost'],
                            'products_cost': costs['products_cost'],
                            'total_cost': costs['total_cost'],
                        }
                    )

                except models.FulfillmentCost.MultipleObjectsReturned:
                    models.FulfillmentCost.objects.filter(
                        store_content_type=store_content_type,
                        store_object_id=track.store.id,
                        order_id=track.order_id,
                        source_id=track.source_id,
                    ).delete()

                    continue

                break

        return costs


def get_profit_details(store, store_type, date_range, limit=20, page=1, orders_map=None, refunds_list=None, user_timezone=''):
    """
    Returns each refund, order and aliexpress fulfillment sorted by date
    """
    start, end = date_range
    store_content_type = ContentType.objects.get_for_model(store)
    sync = models.ProfitSync.objects.get(
        store_content_type=store_content_type,
        store_object_id=store.id
    )

    if not orders_map:
        orders = sync.orders.filter(date__range=(start, end))

        # Get FB orders
        if store_type == 'fb':
            filters_config = {}
            filters_config['after'], filters_config['before'] = start.strftime('%x'), end.strftime('%x')
            orders = fb_utils.FBOrderListQuery(store.user, store, filters_config).items()
            for order in orders:
                order.order_id = order.id
                order.amount = order.total
                order.order_name = order.number

        # Get Google orders
        if store_type == 'google':
            filters_config = {}
            filters_config['after'], filters_config['before'] = start.strftime('%x'), end.strftime('%x')
            orders = google_utils.GoogleOrderListQuery(store.user, store, filters_config).items()
            for order in orders:
                order.order_id = order.id
                order.amount = order.total
                order.order_name = order.number

        orders_map = {order.order_id: get_order_mappings(order, user_timezone) for order in orders}

    if not refunds_list:
        refunds_list = sync.refunds.filter(date__range=(start, end))

    # Merge refunds with orders
    new_refunds = {}  # For refunds done later than order.created_at
    for refund in refunds_list:
        order_id = refund.order_id
        refund_date = arrow.get(refund.date)
        order_date = orders_map.get(order_id, {}).get('date')

        # Refunded products
        # refunded_products = [i.get('line_item') for i in refund.get('refund_line_items', [])]

        # Same refund.date as order.date shows at the same row
        if order_date and order_date.date() == refund.date.date():
            orders_map[order_id]['total_refund'] -= refund.amount
            orders_map[order_id]['profit'] -= refund.amount
            # orders_map[order_id]['refunded_products'] += refunded_products
        else:
            refunds_key = '{}-{}'.format(refund_date.format('YYYY-MM-DD'), order_id)
            if refunds_key not in new_refunds:
                new_refunds[refunds_key] = {
                    'date': refund_date.datetime,
                    'date_as_string': refund_date.format('MM/DD/YYYY'),
                    'order_id': refund.get('order_id'),
                    'profit': 0.0,
                    'total_refund': 0.0,
                    # 'refunded_products': [],
                }

            new_refunds[refunds_key]['profit'] -= refund.amount
            new_refunds[refunds_key]['total_refund'] -= refund.amount
            # new_refunds[refunds_key]['refunded_products'] += refunded_products

    # Paginate profit details
    profit_details = list(orders_map.values()) + list(new_refunds.values())
    profit_details = sorted(profit_details, key=lambda k: k['date'], reverse=True)
    paginator = SimplePaginator(profit_details, limit)
    page = min(max(1, page), paginator.num_pages)
    profit_details = paginator.page(page)

    # Get track for orders being shown
    order_ids = [i.get('order_id') for i in profit_details]
    tracks_map = {}
    existing_order_tracks = []
    StoreOrderTrackModel = get_store_order_track(store_type)
    for track in StoreOrderTrackModel.objects.filter(store=store, order_id__in=order_ids):
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

    # Merge tracks with orders
    for detail in profit_details:
        order_id = detail.get('order_id')
        row_with_order = 'total_price' in detail

        if row_with_order:  # Only get tracks and line items if not just a refund
            order_tracks = tracks_map.get(order_id, [])
            fulfillment_cost = reduce(sum_costs, order_tracks, 0)

            if fulfillment_cost:
                detail['aliexpress_tracks'] = order_tracks
                detail['profit'] -= fulfillment_cost
                detail['fulfillment_cost'] = fulfillment_cost

        if store_type == 'fb':
            order_id = detail.get('fb_order_id')

        if store_type == 'google':
            order_id = detail.get('google_order_id')

        detail['admin_order_url'] = store.get_admin_order_details(order_id)

    return profit_details, paginator


def get_profits(store, store_type, start, end, user_timezone):
    days = list(arrow.Arrow.range('day', start, end))
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

    store_content_type = ContentType.objects.get_for_model(store)
    sync = models.ProfitSync.objects.get(
        store_content_type=store_content_type,
        store_object_id=store.id
    )

    # Saved Orders
    orders = sync.orders.filter(date__range=(start, end))

    # Get FB orders
    if store_type == 'fb':
        filters_config = {}
        filters_config['after'], filters_config['before'] = start.strftime('%x'), end.strftime('%x')
        orders = fb_utils.FBOrderListQuery(store.user, store, filters_config).items()

    # Get Google orders
    if store_type == 'google':
        filters_config = {}
        filters_config['after'], filters_config['before'] = start.strftime('%x'), end.strftime('%x')
        orders = google_utils.GoogleOrderListQuery(store.user, store, filters_config).items()

    orders_map = {}
    totals_orders_count = 0
    for order in orders:
        order_date = arrow.get(order.date)
        try:
            # Correct our database date to show these at the correct day
            order_date = order_date.to(user_timezone)
        except:
            pass

        date_key = order_date.format('YYYY-MM-DD')
        if date_key not in profits_data:
            continue

        totals_orders_count += 1

        if store_type == 'fb' or store_type == 'google':
            order.order_id = order.id
            order.amount = order.total
            order.order_name = order.number

        orders_map[order.order_id] = get_order_mappings(order, user_timezone)
        order_amount = float(order.amount)

        profits_data[date_key]['profit'] += order_amount
        profits_data[date_key]['revenue'] += order_amount
        profits_data[date_key]['orders_count'] += 1
        profits_data[date_key]['empty'] = False
        profits_data[date_key]['css_empty'] = ''

    # Account for refunds processed within date range
    total_refunds = 0.0
    order_refunds = sync.refunds.filter(date__range=(start, end))

    for refund in order_refunds:
        refund_date = arrow.get(refund.date)
        try:
            # Correct our database date to show these at the correct day
            refund_date = refund_date.to(user_timezone)
        except:
            pass

        date_key = refund_date.format('YYYY-MM-DD')
        if date_key not in profits_data:
            continue

        total_refunds += refund.amount
        profits_data[date_key]['profit'] -= refund.amount
        profits_data[date_key]['revenue'] -= refund.amount
        profits_data[date_key]['empty'] = False
        profits_data[date_key]['css_empty'] = ''

    # Aliexpress/EBay costs
    if store_type == 'fb' or store_type == 'google':
        orders_list = [order.order_id for order in orders]
    else:
        orders_list = orders.values('order_id')
    shippings = models.FulfillmentCost.objects.filter(store_content_type=store_content_type,
                                                      store_object_id=store.id,
                                                      order_id__in=orders_list)

    total_fulfillments_count = 0
    for shipping in shippings:
        if shipping.order_id not in orders_map:
            continue

        date_key = orders_map.get(shipping.order_id, {}).get('date')
        date_key = arrow.get(date_key).format('YYYY-MM-DD')
        if date_key not in profits_data:
            continue

        profits_data[date_key]['profit'] -= safe_float(shipping.total_cost)
        profits_data[date_key]['fulfillment_cost'] += safe_float(shipping.total_cost)
        profits_data[date_key]['fulfillments_count'] += 1
        total_fulfillments_count += 1
        profits_data[date_key]['empty'] = False
        profits_data[date_key]['css_empty'] = ''

    # Facebook Insights
    ad_costs = models.FacebookAdCost.objects.filter(account__access__store_content_type=store_content_type,
                                                    account__access__store_object_id=store.id,
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

        ad_cost_amount = safe_float(ad_cost['spend__sum'])
        profits_data[date_key]['profit'] -= safe_float(ad_cost['spend__sum'])
        profits_data[date_key]['ad_spend'] = ad_cost_amount
        profits_data[date_key]['empty'] = False
        profits_data[date_key]['css_empty'] = ''
        total_ad_costs += ad_cost_amount

    # Other Costs
    other_costs = models.OtherCost.objects.filter(store_content_type=store_content_type,
                                                  store_object_id=store.id,
                                                  date__range=(start.date(), end.date())) \
                                          .extra({'date_key': 'date(date)'}) \
                                          .values('date_key') \
                                          .annotate(Sum('amount')) \
                                          .order_by('date_key')

    for other_cost in other_costs:
        date_key = arrow.get(other_cost['date_key']).format('YYYY-MM-DD')
        if date_key not in profits_data:
            continue

        other_cost_value = safe_float(other_cost['amount__sum'])
        is_empty = profits_data[date_key]['empty']

        profits_data[date_key]['profit'] -= other_cost_value
        profits_data[date_key]['other_costs'] = other_cost_value
        # Other costs might be saved as 0
        profits_data[date_key]['empty'] = is_empty and other_cost_value == 0
        profits_data[date_key]['css_empty'] = ''

    # Totals
    if store_type == 'fb' or store_type == 'google':
        revenue = sum([float(order.total) for order in orders]) or 0.0
    else:
        revenue = orders.aggregate(total=Sum('amount'))['total'] or 0.0
    totals = {
        'revenue': revenue,
        'fulfillment_cost': shippings.aggregate(total=Sum('total_cost'))['total'] or 0.0,
        'ads_spend': total_ad_costs,
        'other_costs': other_costs.aggregate(total=Sum('amount__sum'))['total'] or 0.0,
        'average_profit': 0.0,
        'average_revenue': 0.0,
        'refunds': total_refunds,
    }

    totals['outcome'] = safe_float(totals['fulfillment_cost']) + safe_float(totals['ads_spend']) + safe_float(totals['other_costs'])
    totals['profit'] = safe_float(totals['revenue']) - safe_float(totals['outcome']) - safe_float(total_refunds)
    totals['orders_count'] = totals_orders_count
    totals['fulfillments_count'] = total_fulfillments_count
    totals['orders_per_day'] = totals['orders_count'] / len(days)
    totals['fulfillments_per_day'] = Decimal(total_fulfillments_count / len(days)).quantize(Decimal('.01'))
    totals['profit_margin'] = calculate_profit_margin(totals['revenue'], totals['profit'])
    if totals['orders_count'] != 0:
        totals['average_profit'] = totals['profit'] / totals['orders_count']
        totals['average_revenue'] = totals['revenue'] / totals['orders_count']

    details = get_profit_details(store, store_type, (start, end),
                                 limit=20, page=1, orders_map=orders_map,
                                 refunds_list=order_refunds,
                                 user_timezone=user_timezone)

    return list(profits_data.values()), totals, details


def create_facebook_ads(facebook_account, campaign_insight):
    # Using update_or_create for updating insights returned on the same day of last_sync
    models.FacebookAdCost.objects.update_or_create(
        account=facebook_account,
        created_at=campaign_insight['created_at'],
        campaign_id=campaign_insight['campaign_id'],
        defaults={
            'impressions': campaign_insight['impressions'],
            'spend': campaign_insight['spend'],
        }
    )


def get_facebook_ads(facebook_access_id, verbosity=1):
    """ Get Insights from all accounts/campaigns selected from the facebook_access_id
    """
    facebook_access = models.FacebookAccess.objects.get(id=facebook_access_id)

    # Only selected accounts have a corresponding FacebookAccount model
    accounts = facebook_access.accounts.all()
    if verbosity > 1:
        print('Sync {} Facebook AdAccount'.format(len(accounts)))

    for account in accounts:
        if verbosity > 1:
            print('\tSync {} Facebook Campaigns'.format(len(account.campaigns.split(','))))

        # Return already formatted insights
        for insight in account.get_api_insights(verbosity=verbosity):
            create_facebook_ads(account, insight)

        account.save()
