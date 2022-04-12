from django.conf.urls import url

import insider_reports.views

urlpatterns = [
    url(r'^ranked-products$', insider_reports.views.products_list, name='ranked-products'),
    url(r'^ranked-product/(?P<alibaba_product_id>[\d]+)$', insider_reports.views.products_details, name='ranked_product'),
    url(r'^(?P<report_id>[\d]+)/download$', insider_reports.views.download_report, name='download_report'),
]
