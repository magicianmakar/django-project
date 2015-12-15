from django.conf.urls import patterns, include, url
from leadgalaxy.forms import EmailAuthenticationForm
from django.contrib.auth.views import password_reset

import leadgalaxy.views

urlpatterns = patterns('',
    url(r'^$', leadgalaxy.views.index, name='index'),
    url(r'^logout$', leadgalaxy.views.logout),

    url(r'^api/(?P<target>[a-z-]+)$', leadgalaxy.views.api),
    url(r'^product/edit/all$', leadgalaxy.views.bulk_edit, name='bulk_edit'),
    url(r'^product/?(?P<tpl>(grid|table))?$', leadgalaxy.views.product, name='product'),
    url(r'^product/(?P<pid>[0-9]+)$', leadgalaxy.views.product_view, name='product_view'),
    url(r'^product/variants/(?P<store_id>[0-9]+)/(?P<pid>[0-9]+)$', leadgalaxy.views.variants_edit, name='variants_edit'),
    url(r'^boards$', leadgalaxy.views.boards, name='boards'),
    url(r'^shipping/info$', leadgalaxy.views.get_shipping_info, name='get_shipping_info'),
    url(r'^acp/users/list$', leadgalaxy.views.acp_users_list, name='acp_users_list'),
    url(r'^acp/groups$', leadgalaxy.views.acp_groups, name='acp_groups'),
    url(r'^acp/groups/install$', leadgalaxy.views.acp_groups_install, name='acp_groups_install'),
    url(r'^acp/graph$', leadgalaxy.views.acp_graph, name='acp_graph'),
    url(r'^autocomplete/(?P<target>[a-z-]+)$', leadgalaxy.views.autocomplete),
    url(r'^upgrade-required$', leadgalaxy.views.upgrade_required, name='upgrade_required'),
    url(r'^orders$', leadgalaxy.views.orders, name='orders'),

    url(r'^upload/sign_s3$', leadgalaxy.views.upload_file_sign, name='upload_file_sign'),
    url(r'^upload/save_image_s3$', leadgalaxy.views.save_image_s3, name='save_image_s3'),

    url(r'^accounts/register$', leadgalaxy.views.register, name='register'),
    url(r'^accounts/login/$', 'django.contrib.auth.views.login',
        { 'authentication_form': EmailAuthenticationForm }, name='login'),
     url(r'^accounts/password/reset/$', password_reset, {'template_name': 'registration/password_reset.html'}),
     url(r'^accounts/password_reset/done/$', 'django.contrib.auth.views.password_reset_done',
        {'template_name': 'registration/password_reset_done2.html', 'extra_context': {'site_header':'Shopified App'}}),
     url(r'^accounts/password_change/done/$', 'django.contrib.auth.views.password_change_done',
        {'template_name': 'registration/password_change_done2.html', 'extra_context': {'site_header':'Shopified App'}}),

)
