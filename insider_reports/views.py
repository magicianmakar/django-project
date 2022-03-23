from django.contrib.auth.decorators import login_required
import requests
from django.conf import settings
from django.shortcuts import render
from django.urls import reverse
import json
from django.template.defaulttags import register


@register.filter
def get_item(dictionary, key):
    try:
        return dictionary.get(str(key))['key_value']
    except:
        return False


@login_required
def products_list(request):

    if not request.user.can('insider_reports.use'):
        return render(request, 'insider_reports/mock_products_list.html', {'range': range(20)})

    # getting list of available archives
    periods = requests.get(
        settings.INSIDER_REPORT_HOST + 'dropshipping-api/periods',
        verify=False).json()

    price_from = request.GET.get('price_from', '')
    price_to = request.GET.get('price_to', '')

    # getting categories from dropshipping scraper App
    cat_ids = request.GET.getlist('cat_id[]', [])
    cat_id_all = request.GET.get('cat_id_all', False)

    cat_id_url = ''
    if not cat_id_all:

        for cat_id in cat_ids:
            cat_id_url = cat_id_url + f'&category_ids[]={cat_id}'

    page = request.GET.get('page', 1)
    keyword = request.GET.get('keyword', '')
    period_keyword = request.GET.get('period_keyword', '')

    ranked_categories = requests.get(
        settings.INSIDER_REPORT_HOST + 'dropshipping-api/ranked-categories/',
        verify=False).json()

    api_url = f'dropshipping-api/ranked-products?{cat_id_url}&page={page}&keyword={keyword}' \
              f'&year_month={period_keyword}&price_from={price_from}&price_to={price_to}'

    ranked_products = requests.get(
        settings.INSIDER_REPORT_HOST + api_url,
        verify=False).json()

    try:
        alibaba_account_id = request.user.models_user.alibaba.first().alibaba_user_id
    except:
        alibaba_account_id = ''

    return render(request, 'insider_reports/products_list.html', {'ranked_categories': ranked_categories,
                                                                  'ranked_products': ranked_products,
                                                                  'periods': periods,
                                                                  'breadcrumbs': ['Dropshipping Insider Reports'],
                                                                  'cat_ids': cat_ids, 'page': page, 'keyword': keyword,
                                                                  'period_keyword': period_keyword,
                                                                  'alibaba_account_id': alibaba_account_id,
                                                                  'price_from': price_from,
                                                                  'price_to': price_to
                                                                  })


def products_details(request, alibaba_product_id):

    if not request.user.can('insider_reports.use'):
        return render(request, 'insider_reports/mock_products_list.html', )

    api_url = f'dropshipping-api/ranked-products?include_nontop=true&alibaba_product_id={alibaba_product_id}'
    print(api_url)

    try:
        ranked_products = requests.get(
            settings.INSIDER_REPORT_HOST + api_url,
            verify=False).json()
        ranked_product = ranked_products['results'][0]
        ranked_product['data'] = json.loads(ranked_product['data'])
        ranked_product['full_data'] = json.loads(ranked_product['full_data'])

    except:
        ranked_product = False
    ranked_product['big_image'] = False
    for item in ranked_product['full_data']['globalData']['product']['mediaItems']:
        if item['type'] == 'image' and item['imageUrl']:
            ranked_product['big_image'] = item['imageUrl']['big']
            break

    # build sku map
    ranked_product['sku_map'] = {}
    try:
        for key in ranked_product['full_data']['globalData']['product']['sku']['skuInfoMap']:

            # parse optionset
            key_value = ''
            variants = key.split(sep=';')
            for variant in variants:
                variant_values = variant.split(sep=':')
                try:
                    variant_value = variant_values[1]
                except:
                    variant_value = False

                for option in ranked_product['full_data']['globalData']['product']['sku']['skuAttrs']:
                    for value in option['values']:
                        if str(value['id']) == str(variant_value):
                            key_value = key_value + value['name'] + ", "
            key_value = key_value.rstrip(", ")

            ranked_product['sku_map'][str(ranked_product['full_data']['globalData']['product']['sku']
                                          ['skuInfoMap'][key]['id'])] = {'key': key, 'key_value': key_value}
    except:
        # no sku map
        pass
    try:
        alibaba_account_id = request.user.models_user.alibaba.first().alibaba_user_id
    except:
        alibaba_account_id = ''

    if ranked_product['reviews_rank']:
        ranked_product['reviews_rank_percent'] = float(ranked_product['reviews_rank']) / 0.05

    return render(request, 'insider_reports/products_details.html', {'ranked_product': ranked_product,
                                                                     'breadcrumbs': [
                                                                         {'title': 'Dropshipping Insider Reports', 'url': reverse('ranked-products')},
                                                                         f' Product {alibaba_product_id}'],
                                                                     'alibaba_account_id': alibaba_account_id,
                                                                     })
