from django.conf.urls import include, url
from django.conf import settings

from django.contrib import admin
admin.autodiscover()

urlpatterns = [
    url(r'', include('shopified_core.urls')),
    url(r'', include('home.urls')),
    url(r'', include('leadgalaxy.urls')),
    url(r'^shopify/', include('shopify_oauth.urls')),
    url(r'^chq/', include('commercehq_core.urls', 'chq')),
    url(r'^woo/', include('woocommerce_core.urls', 'woo')),
    url(r'^gear/', include('gearbubble_core.urls', 'gear')),
    url(r'^gkart/', include('groovekart_core.urls', 'gkart')),
    url(r'^bigcommerce/', include('bigcommerce_core.urls', 'bigcommerce')),
    url(r'^subscription/', include('stripe_subscription.urls')),
    url(r'^subscription/shopify/', include('shopify_subscription.urls')),
    url(r'^marketing/', include('product_feed.urls')),
    url(r'^pages/', include('article.urls')),
    url(r'^accounts/', include('django.contrib.auth.urls')),
    url(r'^hijack/', include('hijack.urls')),
    url(r'^order/exports/', include('order_exports.urls')),
    url(r'^order/imports/', include('order_imports.urls')),
    url(r'^profit-dashboard/', include('profit_dashboard.urls')),
    url(r'^subusers/', include('subusers.urls')),
    url(r'^tubehunt/', include('youtube_ads.urls')),
    url(r'^callflex/', include('phone_automation.urls')),
    url(r'^aliextractor/', include('aliextractor.urls')),
    url(r'^sso/', include('sso_core.urls')),
    url(r'^profits/', include('profits.urls', 'profits')),
    url(r'^print-on-demand/', include('prints.urls', 'prints')),
    url(r'^pls/', include('supplements.urls', 'pls')),
    url(r'^dropified-product/', include('dropified_product.urls', 'dropified_product')),
    url(r'^admin/', admin.site.urls),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns.append(url(r'^__debug__/', include(debug_toolbar.urls)))

admin.site.site_header = 'Dropified'
admin.site.login_template = 'registration/login.html'
