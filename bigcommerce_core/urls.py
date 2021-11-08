from django.conf.urls import url, include

import bigcommerce_core.views
import home.views
import subusers.views
import leadgalaxy.views

urlpatterns = [
    url(r'^$', home.views.HomePageView.as_view(), name='index'),

    url(r'^auth$', bigcommerce_core.views.auth, name='bigcommerce_auth'),
    url(r'^load$', bigcommerce_core.views.load, name='bigcommerce_load'),
    url(r'^uninstall$', bigcommerce_core.views.uninstall, name='bigcommerce_uninstall'),

    url(r'^products/?(?P<tpl>(grid|table))?$', bigcommerce_core.views.ProductsList.as_view(), name='products_list'),
    url(r'^products/update$', bigcommerce_core.views.product_alerts, name='product_alerts'),
    url(r'^product/(?P<pk>[0-9]+)$', bigcommerce_core.views.ProductDetailView.as_view(), name='product_detail'),
    url(r'^product/mapping/(?P<pk>[0-9]+)$', bigcommerce_core.views.ProductMappingView.as_view(), name='product_mapping'),
    url(r'^product/mapping/supplier/(?P<pk>[0-9]+)$', bigcommerce_core.views.MappingSupplierView.as_view(), name='mapping_supplier'),
    url(r'^product/mapping/bundle/(?P<pk>[0-9]+)$', bigcommerce_core.views.MappingBundleView.as_view(), name='mapping_bundle'),
    url(r'^autocomplete/(?P<target>[a-z-]+)$', bigcommerce_core.views.autocomplete),
    url(r'^product/variants/(?P<store_id>[0-9]+)/(?P<pid>[0-9]+)$', bigcommerce_core.views.VariantsEditView.as_view(), name='variants_edit'),
    url(r'^orders$', bigcommerce_core.views.OrdersList.as_view(), name='orders_list'),
    url(r'^orders/track$', bigcommerce_core.views.OrdersTrackList.as_view(), name='orders_track'),
    url(r'^profit-dashboard$', bigcommerce_core.views.ProfitDashboardView.as_view(), name='profits'),
    url(r'^boards/list$', bigcommerce_core.views.BoardsList.as_view(), name='boards_list'),
    url(r'^boards/(?P<pk>[0-9]+)$', bigcommerce_core.views.BoardDetailView.as_view(), name='board_detail'),
    url(r'^orders/place$', bigcommerce_core.views.OrderPlaceRedirectView.as_view(), name='orders_place'),

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
        subusers.views.subuser_gkart_store_permissions, name='subuser_gkart_store_permissions'),
    url(r'^subusers/gkart-permissions/(?P<user_id>[0-9]+)/store/(?P<store_id>[0-9]+)$',
        subusers.views.subuser_gkart_store_permissions, name='subuser_gkart_store_permissions'),
    url(r'^subusers/bigcommerce-permissions/(?P<user_id>[0-9]+)/store/(?P<store_id>[0-9]+)$',
        subusers.views.subuser_bigcommerce_store_permissions, name='subuser_bigcommerce_store_permissions'),

    url(r'^user/profile$', leadgalaxy.views.user_profile, name='user_profile'),
    url(r'^user/unlock/(?P<token>[a-z0-9]+)$', leadgalaxy.views.user_unlock, name='user_unlock'),
    url(r'^user/invoices/(?P<invoice_id>[\w-]+)$', leadgalaxy.views.user_invoices, name='user_invoices'),
    url(r'^user/invoices/(?P<invoice_id>[\w-]+)/download$', leadgalaxy.views.user_invoices_download, name='user_invoices_download'),
    url(r'^user/profile/invoices$', leadgalaxy.views.user_profile_invoices, name='user_profile_invoices'),
    url(r'^user/profile/plan/change/(?P<plan_id>[0-9]+)$', leadgalaxy.views.user_plan_change, name='user_plan_change'),
    url(r'^products/collections/(?P<collection>[a-z]+)$', leadgalaxy.views.products_collections, name='products_collections'),

    url(r'^pages/', include('article.urls')),
]
