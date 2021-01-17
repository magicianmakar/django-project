from django.conf.urls import url
from django.urls import path

import django.contrib.auth.views
import leadgalaxy.views
import leadgalaxy.api

urlpatterns = [
    url(r'^logout$', leadgalaxy.views.logout, name="leadgalaxy.views.logout"),

    url(r'^webhook/(?P<provider>[a-z-]+)/(?P<option>[a-z:-]+)/?$', leadgalaxy.views.webhook),
    url(r'^product/edit/(?P<what>[a-z-]+)$', leadgalaxy.views.bulk_edit, name='bulk_edit'),
    url(r'^product/?(?P<tpl>(grid|table))?$', leadgalaxy.views.products_list, name='product'),
    url(r'^product/shopify/migrate$', leadgalaxy.views.shopify_migration, name='shopify_migration'),
    url(r'^product/(?P<pid>[0-9]+)$', leadgalaxy.views.product_view, name='product_view'),
    url(r'^product/variants/(?P<store_id>[0-9]+)/(?P<pid>[0-9]+)$', leadgalaxy.views.variants_edit, name='variants_edit'),
    url(r'^product/mapping/(?P<product_id>[0-9]+)$', leadgalaxy.views.product_mapping, name='product_mapping'),
    url(r'^product/mapping/supplier/(?P<product_id>[0-9]+)$', leadgalaxy.views.mapping_supplier, name='mapping_supplier'),
    url(r'^product/mapping/bundle/(?P<product_id>[0-9]+)$', leadgalaxy.views.mapping_bundle, name='mapping_bundle'),
    url(r'^boards/list$', leadgalaxy.views.boards_list, name='boards_list'),
    url(r'^boards/(?P<board_id>[0-9]+)$', leadgalaxy.views.boards_view, name='boards'),
    url(r'^shipping/info/?$', leadgalaxy.views.get_shipping_info, name='get_shipping_info'),
    url(r'^acp/d-black-users$', leadgalaxy.views.dropified_black_users, name='dropified_black_users'),
    url(r'^autocomplete/(?P<target>[a-z-]+)$', leadgalaxy.views.autocomplete),
    url(r'^upgrade-required$', leadgalaxy.views.upgrade_required, name='upgrade_required'),
    url(r'^orders/?$', leadgalaxy.views.OrdersView.as_view(), name='orders'),
    url(r'^orders/track$', leadgalaxy.views.orders_track, name='orders_track'),
    url(r'^orders/place$', leadgalaxy.views.orders_place, name='orders_place'),
    url(r'^locate/(?P<what>[a-z-]+)$', leadgalaxy.views.locate),
    url(r'^products/update$', leadgalaxy.views.product_alerts, name='product_alerts'),
    url(r'^bundles/(?P<bundle_id>[a-z0-9]+)$', leadgalaxy.views.bundles_bonus, name='bundles_bonus'),
    url(r'^products/collections/(?P<collection>[a-z]+)$', leadgalaxy.views.products_collections, name='products_collections'),
    url(r'^upload/sign_s3$', leadgalaxy.views.upload_file_sign, name='upload_file_sign'),
    url(r'^upload/save_image_s3$', leadgalaxy.views.save_image_s3, name='save_image_s3'),

    url(r'^user/profile$', leadgalaxy.views.user_profile, name='user_profile'),
    url(r'^user/unlock/(?P<token>[a-z0-9]+)$', leadgalaxy.views.user_unlock, name='user_unlock'),
    url(r'^user/invoices/(?P<invoice_id>[\w-]+)$', leadgalaxy.views.user_invoices, name='user_invoices'),
    url(r'^user/invoices/(?P<invoice_id>[\w-]+)/download$', leadgalaxy.views.user_invoices_download, name='user_invoices_download'),
    url(r'^user/profile/invoices$', leadgalaxy.views.user_profile_invoices, name='user_profile_invoices'),

    url(r'^accounts/register/?(?P<registration>[a-z0-9-]+)?$', leadgalaxy.views.register, name='register'),
    url(r'^accounts/sudo/$', leadgalaxy.views.sudo_login, name='sudo_login'),
    url(r'^accounts/login/user/$', leadgalaxy.views.user_login_view, name='login'),
    path('accounts/password/setup/<str:register_id>', leadgalaxy.views.account_password_setup, name='account_password_setup'),

    url(r'^accounts/password/reset/$', django.contrib.auth.views.PasswordResetView.as_view(
        template_name='registration/password_reset.html', html_email_template_name='registration/password_reset_email2.html')),
    url(r'^accounts/password_reset/done/$', django.contrib.auth.views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done2.html', extra_context={'site_header': 'Dropified'})),
    url(r'^accounts/password_change/done/$', django.contrib.auth.views.PasswordChangeDoneView.as_view(
        template_name='registration/password_change_done2.html', extra_context={'site_header': 'Dropified'})),
    url(r'^accounts/reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        django.contrib.auth.views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm2.html',
                                                                   extra_context={'site_header': 'Dropified'}), name='password_reset_confirm'),
    url(r'^accounts/reset/done/$', django.contrib.auth.views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete2.html', extra_context={'site_header': 'Dropified'}), name='password_reset_complete'),
]
