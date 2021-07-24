from leadgalaxy.utils import safe_float
from fulfilment_fee.models import SaleTransactionFee
from profit_dashboard.utils import get_costs_from_track
from django.core.cache import cache
import requests
import re
import simplejson as json
from lib.exceptions import capture_exception
from supplements.models import PLSOrderLine
from django.db.models import Sum


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
                total_items = PLSOrderLine.objects.filter(store_order_id=source.order_id).\
                    aggregate(Sum('quantity'))['quantity__sum']
                sales_fee_value += fee_flat * total_items

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
        costs = get_costs_from_track(instance, commit=False)
        instance_type = type(instance).__name__
        instance_status_column = {
            'ShopifyOrderTrack': 'shopify_status',
            'BigCommerceOrderTrack': 'bigcommerce_status',
            'GrooveKartOrderTrack': 'groovekart_status',
            'WooOrderTrack': 'woocommerce_status',
            'CommerceHQOrderTrack': 'commercehq_status',
            'BasketOrderTrack': 'basket_order_status'
        }

        if instance.user.can('sales_fee.use') \
                and (instance.user.is_superuser or not instance.user.can('disabled_sales_fee.use')) \
                and costs and (instance.auto_fulfilled or instance.source_type == 'supplements') \
                and getattr(instance, instance_status_column[instance_type]) == 'fulfilled':

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
