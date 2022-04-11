import json
import requests
from io import BytesIO
from pdfrw import PageMerge, PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.defaulttags import register
from django.urls import reverse

from shopified_core import permissions

from .models import InsiderReport


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


@login_required
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


@login_required
def download_report(request, report_id):
    if not request.user.can('download_insider_report.use'):
        raise permissions.PermissionDenied()

    report = get_object_or_404(InsiderReport, pk=report_id)
    pdf_data = BytesIO(requests.get(report.report_url).content)
    base_pdf = PdfReader(pdf_data)

    pdfmetrics.registerFont(TTFont('Poppins', 'app/static/fonts/Poppins-Bold.ttf'))

    name_string = 'Exclusively for Dropified Members'
    if request.user.get_full_name():
        name_string = f'Exclusively for {request.user.get_full_name()}'

    data = BytesIO()
    c = canvas.Canvas(data)
    c.setPageSize((595, 842))
    c.setFillColorRGB(255, 255, 255)
    c.setFont('Poppins', 16)
    c.drawCentredString((c._pagesize[0] / 2) + 15, c._pagesize[1] / 2, name_string)
    c.save()
    data.seek(0)

    reader = PdfReader(data)
    writer = PdfWriter()
    writer.addpage(reader.pages[0])
    blank_page = BytesIO()
    writer.write(blank_page)
    blank_page.seek(0)

    pdf = PdfReader(blank_page)
    pdf_pages = PageMerge() + pdf.pages

    pdf_page = pdf_pages[0]

    page_merge = PageMerge(base_pdf.pages[0]).add(pdf_page)
    pdf_obj = page_merge[-1]
    pdf_obj.y = 190

    page_merge.render()

    output = BytesIO()
    PdfWriter().write(output, base_pdf)

    output.seek(0)

    file_name = f'Insiders Report {report.report_name}'
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{file_name}.pdf"'
    response.write(output.read())

    return response
