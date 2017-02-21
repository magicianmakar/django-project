from django.conf.urls import patterns, url

import commercehq_core.views

urlpatterns = patterns(
    '',
    url(r'^$', commercehq_core.views.index_view, name='index'),
    url(r'^products/?(?P<tpl>(grid|table))?$', commercehq_core.views.ProductsList.as_view(), name='products_list'),
    url(r'^products/(?P<pk>[0-9]+)$', commercehq_core.views.ProductDetailView.as_view(), name='product_detail'),
    url(r'^store-create$', commercehq_core.views.store_create, name='store_create'),
    url(r'^store-update/(?P<store_id>[0-9]+)$', commercehq_core.views.store_update, name='store_update'),
    url(r'^store-delete/(?P<store_id>[0-9]+)$', commercehq_core.views.store_delete, name='store_delete'),
)
