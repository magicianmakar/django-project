from django.conf.urls import patterns, url

import woocommerce_core.views

urlpatterns = patterns(
    '',
    url(r'^$', woocommerce_core.views.StoresList.as_view(), name='index'),
    url(r'^products/?(?P<tpl>(grid|table))?$', woocommerce_core.views.ProductsList.as_view(), name='products_list'),
    url(r'^product/(?P<pk>[0-9]+)$', woocommerce_core.views.ProductDetailView.as_view(), name='product_detail'),
    url(r'^product/mapping/(?P<pk>[0-9]+)$', woocommerce_core.views.ProductMappingView.as_view(), name='product_mapping'),
    url(r'^product/mapping/supplier/(?P<pk>[0-9]+)$', woocommerce_core.views.MappingSupplierView.as_view(), name='mapping_supplier'),
    url(r'^product/variants/(?P<store_id>[0-9]+)/(?P<pid>[0-9]+)$', woocommerce_core.views.VariantsEditView.as_view(), name='variants_edit'),
    url(r'^orders$', woocommerce_core.views.OrdersList.as_view(), name='orders_list'),
    url(r'^orders/track$', woocommerce_core.views.OrdersTrackList.as_view(), name='orders_track'),
    url(r'^boards/list$', woocommerce_core.views.BoardsList.as_view(), name='boards_list'),
    url(r'^boards/(?P<pk>[0-9]+)$', woocommerce_core.views.BoardDetailView.as_view(), name='board_detail'),
)
