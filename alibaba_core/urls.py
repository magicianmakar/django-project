from django.urls import path

import alibaba_core.views

app_name = 'alibaba_core'

urlpatterns = [
    path('callback/', alibaba_core.views.AccessTokenRedirectView.as_view(), name='access_token_callback'),
    path('products/', alibaba_core.views.Products.as_view(), name='products'),
    path('category/<category_id>/', alibaba_core.views.CategoryProducts.as_view(), name='category_products'),
]
