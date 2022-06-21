from django.conf.urls import include, url

import google_core.views as google_views
import home.views
import leadgalaxy.views
import subusers.views

urlpatterns = [
    url(r'^$', home.views.HomePageView.as_view(), name='index'),
    url(r'^accept-auth/(?P<store_index>[0-9]*)$', google_views.AuthAcceptRedirectView.as_view(), name='auth'),
    url(r'^onboard/(?P<pk>[0-9]+)$', google_views.CompleteAuthView.as_view(), name='onboard'),
    url(r'^products/?(?P<tpl>(grid|table))?$', google_views.ProductsList.as_view(), name='products_list'),
    url(r'^product/(?P<store_index>[0-9]+)/(?P<pk>(.*?))$', google_views.ProductDetailView.as_view(), name='product_detail'),
    url(r'^product/mapping/(?P<store>[0-9]+)/(?P<pk>(.*?))$', google_views.ProductMappingView.as_view(), name='product_mapping'),
    url(r'^product/mapping/supplier/(?P<store>[0-9]+)/(?P<pk>(.*?))', google_views.MappingSupplierView.as_view(), name='mapping_supplier'),
    url(r'^product/mapping/bundle/(?P<pk>[0-9]+)$', google_views.MappingBundleView.as_view(), name='mapping_bundle'),
    url(r'^product/variants/(?P<store_id>[0-9]+)/(?P<pk>(.*?))$', google_views.VariantsEditView.as_view(), name='variants_edit'),
    url(r'^orders$', google_views.OrdersList.as_view(), name='orders_list'),
    url(r'^orders/track$', google_views.OrdersTrackList.as_view(), name='orders_track'),
    url(r'^profit-dashboard$', google_views.ProfitDashboardView.as_view(), name='profits'),
    url(r'^boards/list$', google_views.BoardsList.as_view(), name='boards_list'),
    url(r'^boards/(?P<pk>[0-9]+)$', google_views.BoardDetailView.as_view(), name='board_detail'),
    url(r'^orders/place$', google_views.OrderPlaceRedirectView.as_view(), name='orders_place'),

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

    url(r'^user/profile$', leadgalaxy.views.user_profile, name='user_profile'),
    url(r'^user/unlock/(?P<token>[a-z0-9]+)$', leadgalaxy.views.user_unlock, name='user_unlock'),
    url(r'^user/invoices/(?P<invoice_id>[\w-]+)$', leadgalaxy.views.user_invoices, name='user_invoices'),
    url(r'^user/invoices/(?P<invoice_id>[\w-]+)/download$', leadgalaxy.views.user_invoices_download, name='user_invoices_download'),
    url(r'^user/profile/invoices$', leadgalaxy.views.user_profile_invoices, name='user_profile_invoices'),
    url(r'^products/collections/(?P<collection>[a-z]+)$', leadgalaxy.views.products_collections, name='products_collections'),

    url(r'^pages/', include('article.urls')),
]
