from django.urls import path

import logistics.views

app_name = 'logistics'

urlpatterns = [
    path('products', logistics.views.ProductsListView.as_view(), name='products'),
    path('product', logistics.views.ProductView.as_view(), name='product'),
    path('product/<int:pk>', logistics.views.ProductView.as_view(), name='product'),
    path('supplier/<int:supplier_id>', logistics.views.ProductView.as_view(), name='supplier'),
    path('warehouses', logistics.views.WarehousesListView.as_view(), name='warehouses'),
    path('carriers', logistics.views.CarriersListView.as_view(), name='carriers'),
    path('orders', logistics.views.OrdersListView.as_view(), name='orders'),
    path('orders/<int:order_id>', logistics.views.OrdersListView.as_view(), name='order'),
    path('label/<int:order_id>.png', logistics.views.label, name='label'),
]
