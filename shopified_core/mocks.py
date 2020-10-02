import json
from decimal import Decimal
from collections import OrderedDict
from random import randint, randrange, uniform, choice, getrandbits, shuffle

import arrow
from django.utils.text import Truncator

from profit_dashboard.utils import calculate_profits, calculate_profit_margin
from shopified_core.utils import dict_val


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super(DecimalEncoder, self).default(o)


def get_mocked_profits(store):
    start = arrow.get().replace(days=-30)
    end = arrow.get()
    days = list(arrow.Arrow.range('day', start, end))
    profits_data = OrderedDict()
    totals = {'revenue': 0, 'fulfillment_cost': 0, 'ads_spend': 0, 'other_costs': 0,
              'refunds': 0, 'orders_count': 0, 'fulfillments_count': 0}
    for day in reversed(days):
        date_key = day.format('YYYY-MM-DD')
        data = {
            'date_as_string': day.format('MM/DD/YYYY'),
            'date_as_slug': date_key,
            'week_day': day.strftime('%A'),
            'empty': False,
            'css_empty': '',
            'orders_count': randrange(10, 30),
            'revenue': Decimal(uniform(350, 500)).quantize(Decimal('.01')),
            'other_costs': Decimal(uniform(1, 20)).quantize(Decimal('.01')),
            # Percentages
            'fulfillment_cost': Decimal(randrange(5, 20)) / 100,
            'ad_spend': Decimal(randrange(20, 50)) / 100,
        }

        data['fulfillment_cost'] = data['revenue'] * data['fulfillment_cost']
        data['ad_spend'] = data['revenue'] * data['ad_spend']
        data['fulfillments_count'] = data['orders_count'] - randrange(0, 2)
        profits_data[date_key] = data

        totals['revenue'] += data['revenue']
        totals['fulfillment_cost'] += data['fulfillment_cost']
        totals['ads_spend'] += data['ad_spend']
        totals['other_costs'] += data['other_costs']
        totals['orders_count'] += data['orders_count']
        totals['fulfillments_count'] += data['fulfillments_count']

    total_days = len(days)
    totals['outcome'] = totals['fulfillment_cost'] + totals['ads_spend'] + totals['other_costs']
    totals['profit'] = totals['revenue'] - totals['outcome'] - totals['refunds']
    totals['orders_per_day'] = Decimal(totals['orders_count'] / total_days).quantize(Decimal('.01'))
    totals['fulfillments_per_day'] = Decimal(totals['fulfillments_count'] / total_days).quantize(Decimal('.01'))
    totals['profit_margin'] = calculate_profit_margin(totals['revenue'], totals['profit'])
    totals['average_profit'] = totals['profit'] / totals['orders_count']
    totals['average_revenue'] = totals['revenue'] / totals['orders_count']

    profits = calculate_profits(list(profits_data.values()))

    return {
        'profits': profits,
        'start': start.strftime('%m/%d/%Y'),
        'end': end.strftime('%m/%d/%Y'),
        'current_page': 1,
        'paginator': None,
        'totals': totals,
        'store': store,
        'profits_json': json.dumps(profits[::-1], cls=DecimalEncoder),
        'user_facebook_permission': True,
        'upsell': True,
        'page': 'profit_dashboard',
    }


def get_mocked_config_alerts():
    return {
        'alert_price_change': choice(['notify', 'update']),
        'alert_quantity_change': choice(['notify', 'update', 'none']),
        'alert_product_disappears': choice(['notify', 'unpublish', 'zero_quantity', 'none']),
        'alert_variant_disappears': choice(['notify', 'remove', 'zero_quantity', 'none']),
        'alert_order_cancelled': choice(['none', 'notify']),
        'send_alerts_to_subusers': bool(getrandbits(1)),
        'price_update_method': choice(['global_markup', 'custom_markup', 'same_margin']),
        'price_update_for_increase': bool(getrandbits(1)),
    }


def get_mocked_supplier_variants(all_variants_mapping):
    shipping_map = {}
    mapping_config = {'supplier': 'advanced'}
    supplier_mapping = {}
    countries = {'US': 'United States', 'CA': 'Canada', 'GB': 'United Kingdom',
                 'AU': 'Australia', 'JP': 'Japan'}
    for supplier_id, variants in all_variants_mapping.items():
        for variant_id, variant_options in variants.items():
            shipping = []
            country_choices = ['US', 'CA', 'GB', 'AU', 'JP']
            countries_count = randrange(1, len(country_choices))
            shuffle(country_choices)
            for country_iso in country_choices[:countries_count]:
                price = Decimal(randrange(500, 2000)) / 100
                shipping.append({
                    'country': country_iso,
                    'country_name': countries[country_iso],
                    'method': '1',
                    'method_name': f"{choice(['ePacket', 'EMS', 'DHL', 'Fedex'])} (${price})"
                })
            shipping_map[f"{supplier_id}_{variant_id}"] = shipping
            supplier_mapping[variant_id] = {'supplier': supplier_id, 'shipping': shipping}

    return shipping_map, mapping_config, supplier_mapping


def get_mocked_bundle_variants(product, bundle_mapping):
    new_bundles = []
    for variant in bundle_mapping:
        variant_title = dict_val(variant, ['title', 'variant', 'variant_name'])
        if isinstance(variant_title, list):
            variant_title = variant_title[0]

        if not variant_title and variant.get('option_values'):
            variant_title = ' | '.join([o['label']
                                        for o in variant.get('option_values')
                                        if o.get('label')])

        image = dict_val(variant, ['image', 'image_url'])
        if isinstance(image, dict):
            image = dict_val(image, ['path', 'src'])

        variant['products'] = [{
            'id': product.id,
            'title': product.title,
            'short_title': Truncator(product.title).words(40),
            'image': image,
            'variant_id': str(variant['id']),
            'variant_title': variant_title,
            'variant_image': variant.get('image'),
            'quantity': randrange(2, 5)
        }]

        new_bundles.append(variant)
        if len(new_bundles) == 3:
            break

    return new_bundles


def get_mocked_alert_changes(product_queryset):
    products = product_queryset.all().order_by('?')[:3]

    def random_integer():
        return randint(1, 500)

    def random_float():
        return Decimal(uniform(20, 50)).quantize(Decimal('.01'))

    def random_float_higher():
        return Decimal(uniform(20, 50)).quantize(Decimal('.01'))

    def get_random_change(sku_readable=''):
        random_change = choice([
            {'product': {'offline': [{}]}},
            {'variants': {'var_added': [{'sku_readable': sku_readable}]}},
            {'variants': {'var_removed': [{'sku_readable': sku_readable}]}},
            {'variants': {'quantity': [{
                'old_value': random_integer(), 'new_value': random_integer(),
                'shopify_value': random_integer(), 'chq_value': random_integer(),
                'woo_value': random_integer(), 'gkart_value': random_integer(),
                'bigcommerce_value': random_integer(), 'sku_readable': sku_readable,
            }]}},
            {'variants': {'price': [{
                'level': 'variant', 'name': 'price', 'new_value': random_float(),
                'old_value': random_float(), 'bigcommerce_value': random_float_higher(),
                'gkart_value': random_float_higher(), 'woo_value': random_float_higher(),
                'chq_value': random_float_higher(), 'shopify_value': random_float_higher(),
                'sku_readable': sku_readable,
            }]}},
        ])
        change_object = next(iter(random_change))
        change_type = next(iter(random_change[change_object]))
        return random_change, change_object, change_type

    def get_product_change(variant_names):
        change = {}
        for variant_name in variant_names:
            random_change, change_object, change_type = get_random_change(variant_name)

            if not change.get(change_object):
                change[change_object] = {}

            if not change[change_object].get(change_type):
                change[change_object][change_type] = []

            change[change_object][change_type] += random_change[change_object][change_type]
        return change

    variant_names = ['Small', 'Long Sleeves', 'Extra Large', 'Large', 'Medium']
    default_change = {
        'qelem': {
            'product': {'title': 'Leather Jacket'},
            'updated_at': arrow.get().datetime
        },
        'changes': get_product_change(variant_names)
    }

    product_changes = []
    for product in products:
        try:
            variants = product.get_variant_mapping()
            try:
                variant_names = [' - '.join(i['title'] for i in z) for z in variants.values()][:6]
            except:
                variant_names = ['Default Title']

            product_changes.append({
                'qelem': {
                    'product': {'title': product.title},
                    'updated_at': arrow.get().datetime
                },
                'changes': get_product_change(variant_names)
            })
        except:
            pass

    return product_changes or [default_change]
