from django.conf.urls import patterns, url
from leadgalaxy.forms import EmailAuthenticationForm
from django.contrib.auth.views import password_reset

import leadgalaxy.views
import leadgalaxy.api

urlpatterns = patterns(
    '',
    url(r'^$', leadgalaxy.views.index_view, name='index'),
    url(r'^logout$', leadgalaxy.views.logout),

    url(r'^webhook/(?P<provider>[a-z-]+)/(?P<option>[a-z:-]+)/?$', leadgalaxy.views.webhook),
    url(r'^product/edit/(?P<what>[a-z-]+)$', leadgalaxy.views.bulk_edit, name='bulk_edit'),
    url(r'^product/?(?P<tpl>(grid|table))?$', leadgalaxy.views.products_list, name='product'),
    url(r'^product/(?P<pid>[0-9]+)$', leadgalaxy.views.product_view, name='product_view'),
    url(r'^product/variants/(?P<store_id>[0-9]+)/(?P<pid>[0-9]+)$', leadgalaxy.views.variants_edit, name='variants_edit'),
    url(r'^product/mapping/(?P<product_id>[0-9]+)$', leadgalaxy.views.product_mapping, name='product_mapping'),
    url(r'^product/mapping/supplier/(?P<product_id>[0-9]+)$', leadgalaxy.views.mapping_supplier, name='mapping_supplier'),
    url(r'^product/mapping/bundle/(?P<product_id>[0-9]+)$', leadgalaxy.views.mapping_bundle, name='mapping_bundle'),
    url(r'^boards/list$', leadgalaxy.views.boards_list, name='boards_list'),
    url(r'^boards/(?P<board_id>[0-9]+)$', leadgalaxy.views.boards, name='boards'),
    url(r'^shipping/info$', leadgalaxy.views.get_shipping_info, name='get_shipping_info'),
    url(r'^acp/users/list$', leadgalaxy.views.acp_users_list, name='acp_users_list'),
    url(r'^acp/users/emails$', leadgalaxy.views.acp_users_emails, name='acp_users_emails'),
    url(r'^acp/groups$', leadgalaxy.views.acp_groups, name='acp_groups'),
    url(r'^acp/groups/install$', leadgalaxy.views.acp_groups_install, name='acp_groups_install'),
    url(r'^acp/graph$', leadgalaxy.views.acp_graph, name='acp_graph'),
    url(r'^autocomplete/(?P<target>[a-z-]+)$', leadgalaxy.views.autocomplete),
    url(r'^upgrade-required$', leadgalaxy.views.upgrade_required, name='upgrade_required'),
    url(r'^orders$', leadgalaxy.views.orders_view, name='orders'),
    url(r'^orders/track$', leadgalaxy.views.orders_track, name='orders_track'),
    url(r'^orders/place$', leadgalaxy.views.orders_place, name='orders_place'),
    url(r'^locate/(?P<what>[a-z-]+)$', leadgalaxy.views.locate),
    url(r'^products/update$', leadgalaxy.views.product_alerts, name='product_alerts'),
    url(r'^bundles/(?P<bundle_id>[a-z0-9]+)$', leadgalaxy.views.bundles_bonus, name='bundles_bonus'),
    url(r'^products/collections/(?P<collection>[a-z]+)$', leadgalaxy.views.products_collections, name='products_collections'),
    url(r'^subusers$', leadgalaxy.views.subusers, name='subusers'),
    url(r'^subusers/permissions/(?P<user_id>[0-9]+)$', leadgalaxy.views.subusers_perms, name='subusers_perms'),
    url(r'^subusers/permissions/(?P<user_id>[0-9]+)/edit$', leadgalaxy.views.subuser_perms_edit, name='subuser_perms_edit'),
    url(r'^subusers/permissions/(?P<user_id>[0-9]+)/store/(?P<store_id>[0-9]+)$',
        leadgalaxy.views.subuser_store_permissions, name='subuser_store_permissions'),
    url(r'^subusers/chq-permissions/(?P<user_id>[0-9]+)/store/(?P<store_id>[0-9]+)$',
        leadgalaxy.views.subuser_chq_store_permissions, name='subuser_chq_store_permissions'),
    url(r'^subusers/woo-permissions/(?P<user_id>[0-9]+)/store/(?P<store_id>[0-9]+)$',
        leadgalaxy.views.subuser_woo_store_permissions, name='subuser_woo_store_permissions'),
    url(r'^upload/sign_s3$', leadgalaxy.views.upload_file_sign, name='upload_file_sign'),
    url(r'^upload/save_image_s3$', leadgalaxy.views.save_image_s3, name='save_image_s3'),

    url(r'^pixlr/serve$', leadgalaxy.views.pixlr_serve_image, name='pixlr_serve_image'),
    url(r'^pixlr/close$', leadgalaxy.views.pixlr_close, name='pixlr_close'),

    url(r'^user/profile$', leadgalaxy.views.user_profile, name='user_profile'),
    url(r'^user/unlock/(?P<token>[a-z0-9]+)$', leadgalaxy.views.user_unlock, name='user_unlock'),
    url(r'^user/invoices/(?P<invoice_id>[\w-]+)$', leadgalaxy.views.user_invoices, name='user_invoices'),
    url(r'^user/invoices/(?P<invoice_id>[\w-]+)/download$', leadgalaxy.views.user_invoices_download, name='user_invoices_download'),
    url(r'^user/profile/invoices$', leadgalaxy.views.user_profile_invoices, name='user_profile_invoices'),

    url(r'^accounts/register/?(?P<registration>[a-z0-9-]+)?$', leadgalaxy.views.register, name='register'),
    url(r'^accounts/login/$', 'django.contrib.auth.views.login',
        {'authentication_form': EmailAuthenticationForm}, name='login'),
    url(r'^accounts/password/reset/$', password_reset,
        {'template_name': 'registration/password_reset.html', 'html_email_template_name': 'registration/password_reset_email2.html'}),
    url(r'^accounts/password_reset/done/$', 'django.contrib.auth.views.password_reset_done',
        {'template_name': 'registration/password_reset_done2.html', 'extra_context': {'site_header': 'Dropified'}}),
    url(r'^accounts/password_change/done/$', 'django.contrib.auth.views.password_change_done',
        {'template_name': 'registration/password_change_done2.html', 'extra_context': {'site_header': 'Dropified'}}),

    url(r'^robots\.txt$', leadgalaxy.views.robots_txt, name='robots_txt'),
    url(r'^crossdomain\.xml$', leadgalaxy.views.crossdomain, name='crossdomain'),
)
