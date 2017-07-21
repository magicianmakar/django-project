from django.conf.urls import patterns, include, url

from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns(
    '',
    url(r'', include('shopified_core.urls')),
    url(r'', include('leadgalaxy.urls')),
    url(r'^shopify/', include('shopify_oauth.urls')),
    url(r'^chq/', include('commercehq_core.urls', namespace='chq')),
    url(r'^subscription/', include('stripe_subscription.urls')),
    url(r'^subscription/shopify/', include('shopify_subscription.urls')),
    url(r'^marketing/', include('product_feed.urls')),
    url(r'^pages/', include('article.urls')),
    url(r'^revision/', include('shopify_revision.urls')),
    url(r'^accounts/', include('django.contrib.auth.urls')),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^hijack/', include('hijack.urls')),
    url(r'^order/exports/', include('order_exports.urls')),
    url(r'^order/imports/', include('order_imports.urls')),
)


admin.site.site_header = 'Dropified'
admin.site.login_template = 'registration/login.html'
