from django.conf.urls import include, url
from django.conf import settings

from django.contrib import admin
admin.autodiscover()
admin.site.enable_nav_sidebar = False

urlpatterns = [
    url(r'', include('shopified_core.urls')),
    url(r'', include('home.urls')),
    url(r'', include('leadgalaxy.urls')),
    url(r'^shopify/', include('shopify_oauth.urls')),
    url(r'^chq/', include(('commercehq_core.urls', 'commercehq_core'), 'chq')),
    url(r'^woo/', include(('woocommerce_core.urls', 'woocommerce_core'), 'woo')),
    url(r'^ebay/', include(('ebay_core.urls', 'ebay_core'), 'ebay')),
    url(r'^fb/', include(('facebook_core.urls', 'facebook_core'), 'fb')),
    url(r'^google/', include(('google_core.urls', 'google_core'), 'google')),
    url(r'^gear/', include(('gearbubble_core.urls', 'gearbubble_core'), 'gear')),
    url(r'^gkart/', include(('groovekart_core.urls', 'groovekart_core'), 'gkart')),
    url(r'^bigcommerce/', include(('bigcommerce_core.urls', 'bigcommerce_core'), 'bigcommerce')),
    url(r'^subscription/', include('stripe_subscription.urls')),
    url(r'^subscription/shopify/', include('shopify_subscription.urls')),
    url(r'^marketing/', include('product_feed.urls')),
    url(r'^pages/', include('article.urls')),
    url(r'^hijack/', include('hijack.urls')),
    url(r'^order/exports/', include('order_exports.urls')),
    url(r'^order/imports/', include('order_imports.urls')),
    url(r'^profit-dashboard/', include('profit_dashboard.urls')),
    url(r'^subusers/', include('subusers.urls')),
    url(r'^tubehunt/', include('youtube_ads.urls')),
    url(r'^callflex/', include('phone_automation.urls')),
    url(r'^aliextractor/', include('aliextractor.urls')),
    url(r'^sso/', include('sso_core.urls')),
    url(r'^referral-dashboard/', include('fp_affiliate.urls')),
    url(r'^profits/', include(('profits.urls', 'profits'), 'profits')),
    url(r'^print-on-demand/', include(('prints.urls', 'prints'), 'prints')),
    url(r'^supplements/', include(('supplements.urls', 'supplements'), 'pls')),
    url(r'^dropified-product/', include(('dropified_product.urls', 'dropified_product'), 'dropified_product')),
    url(r'^admin/', admin.site.urls),
    url(r'^tapfiliate/', include('tapfiliate.urls')),
    url(r'^addons/', include('addons_core.urls')),
    url(r'^staff_acp/', include('acp_core.urls')),
    url(r'^fulfilment-fee/', include('fulfilment_fee.urls')),
    url(r'^ckeditor/', include('ckeditor_uploader.urls')),
    url(r'^offer/', include('offers.urls', 'offers')),
    url(r'^alibaba/', include('alibaba_core.urls', 'alibaba')),
    url(r'^aliexpress/', include('aliexpress_core.urls', 'aliexpress')),
    url(r'^logistics/', include('logistics.urls', 'logistics')),
    url(r'^webhook/', include('webhooks.urls')),
    url(r'^products/', include('product_core.urls')),
    url(r'^insider-reports/', include('insider_reports.urls')),
    url(r'^loopedin/', include(('loopedin_core.urls', 'loopedin'), 'loopedin')),
    url(r'^fb-marketplace/', include(('fb_marketplace_core.urls', 'fb_marketplace'), 'fb_marketplace')),
    url(r'^multichannel/', include(('multichannel_products_core.urls', 'multichannel_products_core'), 'multichannel')),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns.append(url(r'^__debug__/', include(debug_toolbar.urls)))

admin.site.site_header = 'Dropified'
admin.site.login_template = 'registration/login.html'
