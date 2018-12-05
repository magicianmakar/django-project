from django.conf.urls import include, url

from django.contrib import admin
admin.autodiscover()

urlpatterns = [
    url(r'', include('shopified_core.urls')),
    url(r'', include('leadgalaxy.urls')),
    url(r'^shopify/', include('shopify_oauth.urls')),
    url(r'^chq/', include('commercehq_core.urls', 'chq')),
    url(r'^woo/', include('woocommerce_core.urls', 'woo')),
    url(r'^gear/', include('gearbubble_core.urls', 'gear')),
    url(r'^subscription/', include('stripe_subscription.urls')),
    url(r'^subscription/shopify/', include('shopify_subscription.urls')),
    url(r'^(lifetime|monthly)/', include('plan_checkout.urls')),
    url(r'^marketing/', include('product_feed.urls')),
    url(r'^pages/', include('article.urls')),
    url(r'^revision/', include('shopify_revision.urls')),
    url(r'^accounts/', include('django.contrib.auth.urls')),
    url(r'^hijack/', include('hijack.urls')),
    url(r'^order/exports/', include('order_exports.urls')),
    url(r'^order/imports/', include('order_imports.urls')),
    url(r'^profit-dashboard/', include('profit_dashboard.urls')),
    url(r'^subusers/', include('subusers.urls')),
    url(r'^zapier/', include('zapier_core.urls')),
    url(r'^tubehunt/', include('youtube_ads.urls')),
    url(r'^admin/', admin.site.urls),
]


admin.site.site_header = 'Dropified'
admin.site.login_template = 'registration/login.html'
