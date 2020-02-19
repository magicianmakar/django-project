from product_common import views as base_views
from .models import Product


class IndexView(base_views.IndexView):
    model = Product
    namespace = 'dropified_product'


class ProductAddView(base_views.ProductAddView):
    model = Product
    namespace = 'dropified_product'
    product_type = 'dropified'


class ProductDetailView(base_views.ProductDetailView):
    namespace = 'dropified_product'


class OrdersShippedWebHookView(base_views.OrdersShippedWebHookView):
    pass


class OrderView(base_views.OrderView):
    pass
