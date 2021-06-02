from django.urls import path

import webhooks.views

urlpatterns = [
    path('jvzoo/<str:option>', webhooks.views.jvzoo_webhook),
    path('zaxaa/<str:option>', webhooks.views.zaxaa_webhook),

    # Shopify Product webhooks
    path('shopify/products-update', webhooks.views.ShopifyProductUpdateWebhook.as_view()),
    path('shopify/products-delete', webhooks.views.ShopifyProductDeleteWebhook.as_view()),

    # Shopify Order Webhooks
    path('shopify/orders-create', webhooks.views.ShopifyOrderCreateWebhook.as_view()),
    path('shopify/orders-updated', webhooks.views.ShopifyOrderUpdateWebhook.as_view()),
    path('shopify/orders-delete', webhooks.views.ShopifyOrderDeleteWebhook.as_view()),

    # Shopify Other Webhooks
    path('shopify/shop-update', webhooks.views.ShopifyShopUpdateWebhook.as_view()),
    path('shopify/app-uninstalled', webhooks.views.ShopifyAppUninstallWebhook.as_view()),

    # Shopify GDPR Webhooks
    path('gdpr-shopify/delete-customer', webhooks.views.ShopifyGDPRDeleteCustomerWebhook.as_view()),
    path('gdpr-shopify/delete-store', webhooks.views.ShopifyGDPRDeleteStoreWebhook.as_view()),

    path('stripe/subs', webhooks.views.stripe_webhook),
    path('clickfunnels/register', webhooks.views.clickfunnels_register),
    path('clickfunnels/checklogin', webhooks.views.clickfunnels_checklogin),
    path('price-monitor/product', webhooks.views.price_monitor_webhook),
    path('slack/command', webhooks.views.slack_webhook),
    path('activecampaign/trial', webhooks.views.activecampaign_trial),
    path('intercom/activecampaign', webhooks.views.intercom_activecampaign),
    path('alibaba/add-product', webhooks.views.alibaba_webhook),
]
