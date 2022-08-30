import json
import re

from django.contrib.contenttypes.models import ContentType
from rest_framework.reverse import reverse

from shopified_core import permissions
from shopified_core.utils import products_filter

from .models import MasterProduct, ProductTemplate


def master_products(request, post_per_page=25, sort=None, board=None):
    sort = request.GET.get('sort')
    res = MasterProduct.objects.filter(user=request.user.models_user)
    res = products_filter(res, request.GET)
    if sort:
        if re.match(r'^-?(title|price)$', sort):
            res = res.order_by(sort)

    return res


def set_master_product(product, master_product_id, user):
    try:
        master_product = MasterProduct.objects.get(id=master_product_id)
        permissions.user_can_edit(user, master_product)

        product.master_product = master_product

        from multichannel_products_core.api import get_helper_class
        helper = get_helper_class(
            product.store.store_type,
            product_id=product.guid if product.store.store_type in ['fb', 'ebay', 'google'] else product.id)
        product.master_variants_map = json.dumps(helper.update_master_variants_map(master_product))
    except MasterProduct.DoesNotExist:
        return


def get_store_child(parent: MasterProduct, store_type, store_id):
    """
    Get master product child from specific store.
    """
    try:
        if store_type == 'bigcommerce':
            return parent.bigcommerceproduct_set.get(store_id=store_id)
        elif store_type == 'chq':
            return parent.commercehqproduct_set.get(store_id=store_id)
        elif store_type == 'ebay':
            return parent.ebayproduct_set.get(store_id=store_id)
        elif store_type == 'fb':
            return parent.fbproduct_set.get(store_id=store_id)
        elif store_type == 'google':
            return parent.googleproduct_set.get(store_id=store_id)
        elif store_type == 'gear':
            return parent.gearbubbleproduct_set.get(store_id=store_id)
        elif store_type == 'gkart':
            return parent.groovekartproduct_set.get(store_id=store_id)
        elif store_type == 'shopify':
            return parent.shopifyproduct_set.get(store_id=store_id)
        elif store_type == 'woo':
            return parent.wooproduct_set.get(store_id=store_id)
    except:
        return None


def get_child_link(child):
    if child.store.store_type == 'shopify':
        return '/product/%d' % child.id
    elif child.store.store_type in ['fb', 'ebay', 'google']:
        return reverse(f'{child.store.store_type}:product_detail',
                       kwargs={'pk': child.guid, 'store_index': child.store.id})
    else:
        return reverse(f'{child.store.store_type}:product_detail', kwargs={'pk': child.id})


def rewrite_master_variants_map(product):
    if product.master_product:
        from multichannel_products_core.api import get_helper_class
        helper = get_helper_class(
            product.store.store_type,
            product_id=product.guid if product.store.store_type in ['fb', 'ebay', 'google'] else product.id)
        product.master_variants_map = json.dumps(helper.update_master_variants_map(product.master_product,
                                                                                   overwrite=False))


def apply_price_template(value, template):
    if template.price_status == 'active_override':
        if template.price_override_amount is not None:
            value = float(template.price_override_amount)

    elif template.price_status == 'active_calculated':
        if not value:
            value = 0
        value = float(value)
        if template.price_amount:
            if template.price_modifier == '$':
                if template.price_direction == '+':
                    value = round(value + float(template.price_amount), 2)
                elif template.price_direction == '-':
                    value = round(value - float(template.price_amount), 2)

            elif template.price_modifier == '%':
                if template.price_direction == '+':
                    value = round(value * (1 + float(template.price_amount) / 100), 2)
                elif template.price_direction == '-':
                    value = round(value * (1 - float(template.price_amount) / 100), 2)
    return value


def apply_compare_price_template(value, template):
    if template.compare_price_status == 'active_override':
        if template.compare_price_override_amount is not None:
            value = float(template.compare_price_override_amount)

    elif template.compare_price_status == 'active_calculated':
        if not value:
            value = 0
        value = float(value)
        if template.compare_price_amount:
            if template.compare_price_modifier == '$':
                if template.compare_price_direction == '+':
                    value = round(value + float(template.compare_price_amount), 2)
                elif template.compare_price_direction == '-':
                    value = round(value - float(template.compare_price_amount), 2)

            elif template.compare_price_modifier == '%':
                if template.compare_price_direction == '+':
                    value = round(value * (1 + float(template.compare_price_amount) / 100), 2)
                elif template.compare_price_direction == '-':
                    value = round(value * (1 - float(template.compare_price_amount) / 100), 2)
    return value


def apply_pricing_template(price, compare_at_price, store):
    store_content_type = ContentType.objects.get_for_model(store)
    pricing_template = ProductTemplate.objects.filter(content_type=store_content_type, object_id=store.id,
                                                      is_active=True, type='pricing').first()
    if pricing_template:
        price = apply_price_template(price, pricing_template)
        compare_at_price = apply_compare_price_template(compare_at_price, pricing_template)
    return price, compare_at_price


def apply_templates(product_data, store, is_suredone=False):
    store_content_type = ContentType.objects.get_for_model(store)

    title_template = ProductTemplate.objects.filter(content_type=store_content_type, object_id=store.id,
                                                    is_active=True, type='title_and_description').first()
    if title_template:
        if 'title' in product_data:
            product_data['title'] = title_template.title.replace('{{ title }}', product_data['title'])
        if is_suredone:
            if 'longdescription' in product_data:
                product_data['longdescription'] = title_template.description.replace('{{ description }}',
                                                                                     product_data['longdescription'])
        else:
            if 'description' in product_data:
                product_data['description'] = title_template.description.replace('{{ description }}',
                                                                                 product_data['description'])

    if is_suredone:
        if 'price' in product_data and 'compareatprice' in product_data:
            product_data['price'], product_data['compareatprice'] = apply_pricing_template(
                product_data['price'], product_data['compareatprice'], store)
    else:
        if 'price' in product_data and 'compare_at_price' in product_data:
            product_data['price'], product_data['compare_at_price'] = apply_pricing_template(
                product_data['price'], product_data['compare_at_price'], store)
    return product_data
