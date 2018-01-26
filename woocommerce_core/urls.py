from django.conf.urls import patterns, url

import woocommerce_core.views
import subusers.views

urlpatterns = patterns(
    '',
    url(r'^$', woocommerce_core.views.StoresList.as_view(), name='index'),
    url(r'^callback-endpoint/(?P<store_hash>[a-z0-9]+)$', woocommerce_core.views.CallbackEndpoint.as_view(), name='callback_endpoint'),
    url(r'^products/?(?P<tpl>(grid|table))?$', woocommerce_core.views.ProductsList.as_view(), name='products_list'),
    url(r'^product/(?P<pk>[0-9]+)$', woocommerce_core.views.ProductDetailView.as_view(), name='product_detail'),
    url(r'^product/mapping/(?P<pk>[0-9]+)$', woocommerce_core.views.ProductMappingView.as_view(), name='product_mapping'),
    url(r'^product/mapping/supplier/(?P<pk>[0-9]+)$', woocommerce_core.views.MappingSupplierView.as_view(), name='mapping_supplier'),
    url(r'^product/variants/(?P<store_id>[0-9]+)/(?P<pid>[0-9]+)$', woocommerce_core.views.VariantsEditView.as_view(), name='variants_edit'),
    url(r'^orders$', woocommerce_core.views.OrdersList.as_view(), name='orders_list'),
    url(r'^orders/track$', woocommerce_core.views.OrdersTrackList.as_view(), name='orders_track'),
    url(r'^boards/list$', woocommerce_core.views.BoardsList.as_view(), name='boards_list'),
    url(r'^boards/(?P<pk>[0-9]+)$', woocommerce_core.views.BoardDetailView.as_view(), name='board_detail'),
    url(r'^orders/place$', woocommerce_core.views.OrderPlaceRedirectView.as_view(), name='orders_place'),

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
