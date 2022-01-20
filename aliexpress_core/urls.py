from django.urls import path

import aliexpress_core.views

app_name = 'aliexpress_core'

urlpatterns = [
    path('oauth/', aliexpress_core.views.AuthorizeView.as_view(), name='aliexpress.oauth'),
    path('token/', aliexpress_core.views.TokenView.as_view(), name='aliexpress.token'),
    path('products/', aliexpress_core.views.Products.as_view(), name='products'),
    path('category/<category_id>/', aliexpress_core.views.CategoryProducts.as_view(), name='category_products'),
]
