from django.conf.urls import patterns, url

import woocommerce_core.views

urlpatterns = patterns(
    '',
    url(r'^$', woocommerce_core.views.StoresList.as_view(), name='index'),
    url(r'^products/?(?P<tpl>(grid|table))?$', woocommerce_core.views.ProductsList.as_view(), name='products_list'),
    url(r'^product/(?P<pk>[0-9]+)$', woocommerce_core.views.ProductDetailView.as_view(), name='product_detail'),
    url(r'^product/mapping/(?P<pk>[0-9]+)$', woocommerce_core.views.ProductMappingView.as_view(), name='product_mapping'),
)
