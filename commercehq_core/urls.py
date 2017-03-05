from django.conf.urls import patterns, url

import commercehq_core.views

urlpatterns = patterns(
    '',
    url(r'^$', commercehq_core.views.StoresList.as_view(), name='index'),
    url(r'^products/?(?P<tpl>(grid|table))?$', commercehq_core.views.ProductsList.as_view(), name='products_list'),
    url(r'^product/(?P<pk>[0-9]+)$', commercehq_core.views.ProductDetailView.as_view(), name='product_detail'),
    url(r'^boards/list$', commercehq_core.views.BoardsList.as_view(), name='boards_list'),
    url(r'^board-create$', commercehq_core.views.board_create, name='board_create'),
    url(r'^board-update/(?P<board_id>[0-9]+)$', commercehq_core.views.board_update, name='board_update'),
    url(r'^store-create$', commercehq_core.views.store_create, name='store_create'),
    url(r'^store-update/(?P<store_id>[0-9]+)$', commercehq_core.views.store_update, name='store_update'),

    url(r'^orders$', commercehq_core.views.OrdersList.as_view(), name='orders_list'),
)
