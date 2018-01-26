from django.conf.urls import patterns, url

import commercehq_core.views
import subusers.views

urlpatterns = patterns(
    '',
    url(r'^$', commercehq_core.views.StoresList.as_view(), name='index'),

    url(r'^store-update/(?P<store_id>[0-9]+)$', commercehq_core.views.store_update, name='store_update'),

    url(r'^products/?(?P<tpl>(grid|table))?$', commercehq_core.views.ProductsList.as_view(), name='products_list'),
    url(r'^product/(?P<pk>[0-9]+)$', commercehq_core.views.ProductDetailView.as_view(), name='product_detail'),
    url(r'^product/mapping/(?P<pk>[0-9]+)$', commercehq_core.views.ProductMappingView.as_view(), name='product_mapping'),
    url(r'^product/mapping/supplier/(?P<pk>[0-9]+)$', commercehq_core.views.MappingSupplierView.as_view(), name='mapping_supplier'),
    url(r'^product/mapping/bundle/(?P<pk>[0-9]+)$', commercehq_core.views.MappingBundleView.as_view(), name='mapping_bundle'),
    url(r'^autocomplete/(?P<target>[a-z-]+)$', commercehq_core.views.autocomplete),

    url(r'^boards/list$', commercehq_core.views.BoardsList.as_view(), name='boards_list'),
    url(r'^boards/(?P<pk>[0-9]+)$', commercehq_core.views.BoardDetailView.as_view(), name='board_detail'),

    url(r'^orders$', commercehq_core.views.OrdersList.as_view(), name='orders_list'),
    url(r'^orders/place$', commercehq_core.views.OrderPlaceRedirectView.as_view(), name='orders_place'),
    url(r'^orders/track$', commercehq_core.views.OrdersTrackList.as_view(), name='orders_track'),

    url(r'^subusers$', subusers.views.subusers, name='subusers'),
    url(r'^subusers/permissions/(?P<user_id>[0-9]+)$', subusers.views.subusers_perms, name='subusers_perms'),
    url(r'^subusers/permissions/(?P<user_id>[0-9]+)/edit$', subusers.views.subuser_perms_edit, name='subuser_perms_edit'),
    url(r'^subusers/permissions/(?P<user_id>[0-9]+)/store/(?P<store_id>[0-9]+)$',
        subusers.views.subuser_store_permissions, name='subuser_store_permissions'),
    url(r'^subusers/chq-permissions/(?P<user_id>[0-9]+)/store/(?P<store_id>[0-9]+)$',
        subusers.views.subuser_chq_store_permissions, name='subuser_chq_store_permissions'),
    url(r'^subusers/woo-permissions/(?P<user_id>[0-9]+)/store/(?P<store_id>[0-9]+)$',
        subusers.views.subuser_woo_store_permissions, name='subuser_woo_store_permissions'),
)
