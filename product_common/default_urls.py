from django.conf.urls import url

import product_common.views

"""
This file isn't used. It is here as a help to setup new local product.
"""

urlpatterns = [
    url(r'^$', product_common.views.IndexView.as_view(), name='index'),

    url(r'^product/add$',
        product_common.views.ProductAddView.as_view(),
        name='product_add'),

    url(r'^product/(?P<product_id>[0-9]+)$',
        product_common.views.ProductDetailView.as_view(),
        name='product_detail'),

    url(r'^shipstation/webhook/order_shipped$',
        product_common.views.OrdersShippedWebHookView.as_view(),
        name='order_shipped_webhook'),

    url(r'^order/list$',
        product_common.views.OrderView.as_view(),
        name='order_list'),

    url(r'^payout/list$',
        product_common.views.PayoutView.as_view(),
        name='payout_list'),
]
