from django.conf.urls import url

import fb_marketplace_core.views
import home.views

urlpatterns = [
    url(r'^$', home.views.HomePageView.as_view(), name='index'),

    url(r'^products/?(?P<tpl>(grid|table))?$', fb_marketplace_core.views.ProductsList.as_view(), name='products_list'),
    url(r'^product/(?P<pk>[0-9]+)$', fb_marketplace_core.views.ProductDetailView.as_view(), name='product_detail'),
    # url(r'^orders$', fb_marketplace_core.views.OrdersList.as_view(), name='orders_list'),
    # url(r'^orders/track$', fb_marketplace_core.views.OrdersTrackList.as_view(), name='orders_track'),
]
