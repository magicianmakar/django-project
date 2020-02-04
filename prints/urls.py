from django.conf.urls import url

import prints.views

urlpatterns = [
    url(r'^$', prints.views.index, name='index'),
    url(r'^products$', prints.views.products, name='products'),
    url(r'^placed-orders$', prints.views.orders, name='orders'),
    url(r'^edit/(?P<product_id>[\d]+)$', prints.views.edit, name='edit'),
    url(r'^edit/(?P<product_id>[\d]+)/(?P<custom_product_id>[\d]+)$', prints.views.edit, name='edit'),
    url(r'^save$', prints.views.save, name='save'),
    url(r'^product/update/(?P<source_id>[\d]+)$', prints.views.product_update, name='product_update'),
    url(r'^source/(?P<custom_product_id>[\d]+)$', prints.views.source, name='source'),
    url(r'^tracking/(?P<order_id>[\d]+)$', prints.views.tracking, name='tracking'),
]
