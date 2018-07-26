from django.conf.urls import patterns, url

import gearbubble_core.views
import subusers.views

urlpatterns = patterns(
    '',
    url(r'^$', gearbubble_core.views.StoresList.as_view(), name='index'),
    url(r'^products/?(?P<tpl>(grid|table))?$', gearbubble_core.views.ProductsList.as_view(), name='products_list'),
    url(r'^product/(?P<pk>[0-9]+)$', gearbubble_core.views.ProductDetailView.as_view(), name='product_detail'),
    url(r'^boards/list$', gearbubble_core.views.BoardsList.as_view(), name='boards_list'),
    url(r'^boards/(?P<pk>[0-9]+)$', gearbubble_core.views.BoardDetailView.as_view(), name='board_detail'),
    url(r'^orders$', gearbubble_core.views.OrdersList.as_view(), name='orders_list'),
    url(r'^orders/place$', gearbubble_core.views.OrderPlaceRedirectView.as_view(), name='orders_place'),
    url(r'^orders/track$', gearbubble_core.views.OrdersTrackList.as_view(), name='orders_track'),
    url(r'^autocomplete/(?P<target>[a-z-]+)$', gearbubble_core.views.autocomplete),
    url(r'^product/variants/(?P<store_id>[0-9]+)/(?P<pid>[0-9]+)$', gearbubble_core.views.VariantsEditView.as_view(), name='variants_edit'),
    url(r'^product/mapping/(?P<pk>[0-9]+)$', gearbubble_core.views.ProductMappingView.as_view(), name='product_mapping'),
    url(r'^product/mapping/supplier/(?P<pk>[0-9]+)$', gearbubble_core.views.MappingSupplierView.as_view(), name='mapping_supplier'),

    url(r'^subusers$', subusers.views.subusers, name='subusers'),
    url(r'^subusers/permissions/(?P<user_id>[0-9]+)$', subusers.views.subusers_perms, name='subusers_perms'),
    url(r'^subusers/permissions/(?P<user_id>[0-9]+)/edit$', subusers.views.subuser_perms_edit, name='subuser_perms_edit'),
    url(r'^subusers/permissions/(?P<user_id>[0-9]+)/store/(?P<store_id>[0-9]+)$',
        subusers.views.subuser_store_permissions, name='subuser_store_permissions'),
    url(r'^subusers/chq-permissions/(?P<user_id>[0-9]+)/store/(?P<store_id>[0-9]+)$',
        subusers.views.subuser_chq_store_permissions, name='subuser_chq_store_permissions'),
    url(r'^subusers/woo-permissions/(?P<user_id>[0-9]+)/store/(?P<store_id>[0-9]+)$',
        subusers.views.subuser_woo_store_permissions, name='subuser_woo_store_permissions'),
    url(r'^subusers/gear-permissions/(?P<user_id>[0-9]+)/store/(?P<store_id>[0-9]+)$',
        subusers.views.subuser_gear_store_permissions, name='subuser_gear_store_permissions'),
)
