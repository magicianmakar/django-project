from django.urls import path

import product_core.views

urlpatterns = [
    path('list', product_core.views.ProductsListView.as_view(), name='products_list_view'),
]
