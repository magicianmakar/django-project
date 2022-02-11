import re
import requests
import simplejson as json

from django.core.cache import cache
from django.db.models import Sum

from fulfilment_fee.models import SaleTransactionFee
from leadgalaxy.utils import safe_float
from lib.exceptions import capture_exception
from profit_dashboard.utils import get_costs_from_track
from supplements.models import PLSOrderLine
from django.utils import timezone
import datetime
import calendar
from django.db.models import Q
from bigcommerce_core.models import BigCommerceOrderTrack
from commercehq_core.models import CommerceHQOrderTrack
from ebay_core.models import EbayOrderTrack
from groovekart_core.models import GrooveKartOrderTrack
from leadgalaxy.models import ShopifyOrderTrack
from my_basket.models import BasketOrderTrack
from woocommerce_core.models import WooOrderTrack

track_types = [
    {'model': ShopifyOrderTrack, 'status_column': 'shopify_status'},
    {'model': BigCommerceOrderTrack, 'status_column': 'bigcommerce_status'},
    {'model': GrooveKartOrderTrack, 'status_column': 'groovekart_status'},
    {'model': WooOrderTrack, 'status_column': 'woocommerce_status'},
    {'model': EbayOrderTrack, 'status_column': 'ebay_status'},
    {'model': CommerceHQOrderTrack, 'status_column': 'commercehq_status'},
    {'model': BasketOrderTrack, 'status_column': 'basket_order_status'},
]


def generate_sale_transaction_fee(source_type, source, amount, currency_data):
    try:
        fee_percent = safe_float(source.user.profile.plan.sales_fee_config.fee_percent)
        fee_flat = safe_float(source.user.profile.plan.sales_fee_config.fee_flat)

        # searching transaction fee
        try:
            SaleTransactionFee.objects.get(
                user=source.user,
                source_model=source_type,
                source_id=source.source_id
            )
        except SaleTransactionFee.DoesNotExist:
            sales_fee_value = safe_float(amount) * safe_float(fee_percent) / 100

            if source.source_type == 'supplements' and fee_flat > 0:
                # per-item flat price for PLS orders
                total_items = PLSOrderLine.objects.filter(store_order_id=source.order_id).\
                    aggregate(Sum('quantity'))['quantity__sum']
                sales_fee_value += fee_flat * total_items
            elif source.source_type != 'supplements' and fee_flat > 0:
                # per-order flat price for non-PLS orders
                sales_fee_value += fee_flat

            # generating full fee when any of order items is fulfilled
            sale_transaction_fee = SaleTransactionFee.objects.create(
                user=source.user,
                source_model=source_type,
                source_id=source.source_id,
                fee_value=sales_fee_value,
                currency_conversion_data=json.dumps(currency_data)
            )
            return sale_transaction_fee
    except:
        capture_exception()
        return None


def process_sale_transaction_fee(instance):
    try:
        for track_type in track_types:
            if track_type['model'] == type(instance):
                status_column = track_type['status_column']

        if not instance.user.can('sales_fee.use') \
            or instance.user.is_superuser \
            or instance.user.is_staff \
            or instance.user.can('disabled_sales_fee.use') \
            or (not instance.auto_fulfilled and instance.source_type != 'supplements') \
                or getattr(instance, status_column) != 'fulfilled':
            return

        # check total order limit if set (OR logic)
        process_fees_trigger = instance.user.profile.plan.sales_fee_config.process_fees_trigger
        monthly_free_limit = instance.user.profile.plan.sales_fee_config.monthly_free_limit
        monthly_free_amount = instance.user.profile.plan.sales_fee_config.monthly_free_amount

        # check limit adjusts in addons
        for addon in instance.user.profile.addons.all():
            monthly_free_limit += addon.sales_fees_adjust_free_limit
            monthly_free_amount += addon.sales_fees_adjust_free_amount

        if process_fees_trigger == 'count' and monthly_free_limit > 0 \
                and get_total_orders(instance.user) < monthly_free_limit:
            # skip if order limit is reached and amount limit is not set
            return False

        if process_fees_trigger == 'amount' and monthly_free_amount > 0 and get_total_amount(instance.user) < monthly_free_amount:
            # skip this fee, limit amount is not reached
            return False

        costs = get_costs_from_track(instance, commit=False)
        instance_type = type(instance).__name__

        if costs:
            # getting sales fee config
            normalized_cost = normalize_currency(costs['products_cost'], costs['currency'])
            currency_data = {
                'original_amount': costs['products_cost'],
                'original_currency': costs['currency']}

            sale_transaction_fee = generate_sale_transaction_fee(instance_type, instance, normalized_cost, currency_data)
            return sale_transaction_fee
    except:
        capture_exception()
        pass


def get_total_orders(user, date_from=False, date_to=False):
    total = 0
    date = timezone.now()
    if not date_from:
        date_from = date.replace(day=1, hour=0, minute=0, second=0)
        date_to = date_from.replace(day=1) + datetime.timedelta(days=calendar.monthrange(date.year, date.month)[1] - 1)

    for track_type in track_types:
        status_filter_dict = {track_type['status_column']: 'fulfilled'}
        total = total + track_type['model'].objects.filter(created_at__gte=date_from, created_at__lte=date_to, user=user).\
            filter(**status_filter_dict).filter(Q(auto_fulfilled=True) | Q(source_type='supplements')).count()

    return total


def get_total_amount(user, date_from=False, date_to=False):
    total = 0
    date = timezone.now()
    if not date_from:
        date_from = date.replace(day=1, hour=0, minute=0, second=0)
        date_to = date_from.replace(day=1) + datetime.timedelta(days=calendar.monthrange(date.year, date.month)[1] - 1)

    for track_type in track_types:
        status_filter_dict = {track_type['status_column']: 'fulfilled'}
        tracks = track_type['model'].objects.filter(created_at__gte=date_from, created_at__lte=date_to, user=user).\
            filter(**status_filter_dict).filter(Q(auto_fulfilled=True) | Q(source_type='supplements')).iterator()
        for track in tracks:
            try:
                costs = get_costs_from_track(track, commit=False)
                if costs:
                    normalized_cost = normalize_currency(costs['products_cost'], costs['currency'])
                    total = total + safe_float(normalized_cost)
            except:
                capture_exception()
                pass

    return total


def get_total_fees(user, date_from=False, date_to=False):
    total = 0
    date = timezone.now()
    if not date_from:
        date_from = date.replace(day=1, hour=0, minute=0, second=0)
        date_to = date_from.replace(day=1) + datetime.timedelta(days=calendar.monthrange(date.year, date.month)[1] - 1)

    total = total + user.saletransactionfee_set.filter(created_at__gte=date_from, created_at__lte=date_to).count()

    return total


def normalize_currency(amount, currency):

    if currency == "US $":
        currency = "USD"
    currency = re.sub(r'\W+', '', currency)
    usd_amount = convert_to_usd(amount, currency)

    return usd_amount


def convert_to_usd(amount, currency):
    rates = cache.get_or_set('currency-rates', get_rates(), 3600)
    try:
        if rates['rates'][currency]:
            amount = safe_float(amount) * safe_float(rates['rates'][currency])
    except KeyError:
        pass
    return amount


def get_rates():
    r = requests.get('https://api.exchangeratesapi.io/latest?base=USD')
    return r.json()
