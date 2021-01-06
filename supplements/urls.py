from django.conf.urls import url

import supplements.views

urlpatterns = [
    url(r'^$', supplements.views.Index.as_view(), name='index'),

    url(r'^supplement/new$',
        supplements.views.Product.as_view(),
        name='product'),

    url(r'^supplement/(?P<supplement_id>[0-9]+)/edit$',
        supplements.views.ProductEdit.as_view(),
        name='product_edit'),

    url(r'^supplement/(?P<supplement_id>[0-9]+)$',
        supplements.views.Supplement.as_view(),
        name='supplement'),

    url(r'^usersupplement/(?P<supplement_id>[0-9]+)$',
        supplements.views.UserSupplementView.as_view(),
        name='user_supplement'),

    url(r'^my/supplement/list$',
        supplements.views.MySupplements.as_view(),
        name='my_supplements'),

    url(r'^my/order/list$',
        supplements.views.MyOrders.as_view(),
        name='my_orders'),

    url(r'^usersupplements/list$',
        supplements.views.AllUserSupplements.as_view(),
        name='all_user_supplements'),

    url(r'^label/(?P<label_id>[0-9]+)$',
        supplements.views.Label.as_view(),
        name='label_detail'),

    url(r'^usersupplement/(?P<supplement_id>[0-9]+)/history$',
        supplements.views.LabelHistory.as_view(),
        name='label_history'),

    url(r'^usersupplements/(?P<supplement_id>[0-9]+)/history$',
        supplements.views.AdminLabelHistory.as_view(),
        name='admin_label_history'),

    url(r'^shipstation/webhook/order_shipped$',
        supplements.views.OrdersShippedWebHook.as_view(),
        name='order_shipped_webhook'),

    url(r'^order/list$',
        supplements.views.Order.as_view(),
        name='order_list'),

    url(r'^order/(?P<order_id>[0-9]+)$$',
        supplements.views.OrderDetail.as_view(),
        name='order_detail'),

    url(r'^my/order/(?P<order_id>[0-9]+)$$',
        supplements.views.MyOrderDetail.as_view(),
        name='my_order_detail'),

    url(r'^payout/list$',
        supplements.views.PayoutView.as_view(),
        name='payout_list'),

    url(r'^payout/(?P<payout_id>[0-9]+)$$',
        supplements.views.PayoutDetail.as_view(),
        name='payout_detail'),

    url(r'^order/item/list$',
        supplements.views.OrderItemListView.as_view(),
        name='orderitem_list'),

    url(r'^line/(?P<line_id>[0-9]+)/label/generate$',
        supplements.views.GenerateLabel.as_view(),
        name='generate_label'),

    url(r'^billing$',
        supplements.views.Billing.as_view(),
        name='billing'),

    url(r'^remove-cc$',
        supplements.views.RemoveCreditCard.as_view(),
        name='remove-cc'),

    url(r'^upload-json$',
        supplements.views.UploadJSON.as_view(),
        name='upload_json'),

    url(r'^download-json$',
        supplements.views.DownloadJSON.as_view(),
        name='download_json'),

    url(r'^autocomplete/(?P<target>[a-z-]+)$',
        supplements.views.Autocomplete.as_view(),
        name='autocomplete'),

    url(r'^reports$',
        supplements.views.Reports.as_view(),
        name='reports'),

    url(r'^my/order/(?P<order_id>[0-9]+)/pdf/generate$',
        supplements.views.GeneratePaymentPDF.as_view(),
        name='generate_payment_pdf'),

    url(r'^basket$',
        supplements.views.Basket.as_view(),
        name='my_basket'),

    url(r'^basket/checkout$',
        supplements.views.BasketCheckout.as_view(),
        name='checkout'),

]
