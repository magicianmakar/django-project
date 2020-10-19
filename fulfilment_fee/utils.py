from leadgalaxy.utils import safe_float
from fulfilment_fee.models import SaleTransactionFee
from profit_dashboard.utils import get_costs_from_track
from django.core.cache import cache
import requests
import re
import simplejson as json


def generate_sale_transaction_fee(source_type, source, amount, currency_data):
    try:
        fee_percent = safe_float(source.user.profile.plan.sales_fee_config.fee_percent)

        sale_transaction_fee = SaleTransactionFee.objects.update_or_create(
            user=source.user,
            source_model=source_type,
            source_id=source.id,
            fee_value=amount * fee_percent / 100,
            currency_conversion_data=json.dumps(currency_data)
        )

        return sale_transaction_fee
    except:
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
        }

        if instance.user.can('sales_fee.use') \
                and (instance.user.is_superuser or not instance.user.can('disabled_sales_fee.use')) \
                and costs and instance.auto_fulfilled and getattr(instance, instance_status_column[instance_type]) == 'fulfilled':
            # getting sales fee config
            normalized_cost = normalize_currency(costs['total_cost'], costs['currency'])

            currency_data = {
                'original_amount': costs['total_cost'],
                'original_currency': costs['currency']}

            generate_sale_transaction_fee(instance_type, instance, normalized_cost, currency_data)
    except:
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
            amount = amount * rates['rates'][currency]
    except KeyError:
        pass
    return amount


def get_rates():
    r = requests.get('https://api.exchangeratesapi.io/latest?base=USD')
    return r.json()
