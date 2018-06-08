from django.conf.urls import patterns, include, url

from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns(
    '',
    url(r'', include('shopified_core.urls')),
    url(r'', include('leadgalaxy.urls')),
    url(r'^shopify/', include('shopify_oauth.urls')),
    url(r'^chq/', include('commercehq_core.urls', namespace='chq')),
    url(r'^woo/', include('woocommerce_core.urls', namespace='woo')),
    url(r'^subscription/', include('stripe_subscription.urls')),
    url(r'^subscription/shopify/', include('shopify_subscription.urls')),
    url(r'^(lifetime|monthly)/', include('plan_checkout.urls')),
    url(r'^marketing/', include('product_feed.urls')),
    url(r'^pages/', include('article.urls')),
    url(r'^revision/', include('shopify_revision.urls')),
    url(r'^accounts/', include('django.contrib.auth.urls')),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^hijack/', include('hijack.urls')),
    url(r'^order/exports/', include('order_exports.urls')),
    url(r'^order/imports/', include('order_imports.urls')),
    url(r'^marketplace/', include('dropwow_core.urls', namespace='marketplace')),
    url(r'^profit-dashboard/', include('profit_dashboard.urls')),
    url(r'^subusers/', include('subusers.urls')),
    url(r'^zapier/', include('zapier_core.urls')),
)


admin.site.site_header = 'Dropified'
admin.site.login_template = 'registration/login.html'
