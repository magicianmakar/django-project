from django.conf.urls import url

import dropified_product.views

urlpatterns = [
    url(r'^$', dropified_product.views.IndexView.as_view(), name='index'),

    url(r'^product/add$',
        dropified_product.views.ProductAddView.as_view(),
        name='product_add'),

    url(r'^product/(?P<product_id>[0-9]+)$',
        dropified_product.views.ProductDetailView.as_view(),
        name='product_detail'),

    url(r'^shipstation/webhook/order_shipped$',
        dropified_product.views.OrdersShippedWebHookView.as_view(),
        name='order_shipped_webhook'),

    url(r'^order/list$',
        dropified_product.views.OrderView.as_view(),
        name='order_list'),
]
