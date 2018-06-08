from django.conf.urls import include, url
from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register(r'hooks', views.HookViewSet)
router.register(r'stores/shopify', views.ShopifyStoreViewSet)
router.register(r'stores/chq', views.CommerceHQStoreViewSet)
router.register(r'products/shopify', views.ShopifyProductViewSet)
router.register(r'products/chq', views.CommerceHQProductViewSet)

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^samples/(?P<event>[a-z_]+)$', views.ZapierSampleList.as_view()),
    url(r'^products/(?P<store_type>[a-z_]+)/(?P<pk>[0-9]+)/update_visibility$', views.ProductVisibilityUpdate.as_view()),
    url(r'^products/(?P<store_type>[a-z_]+)/(?P<pk>[0-9]+)/update_notes$', views.ProductNotesUpdate.as_view()),
    url(r'^products/(?P<store_type>[a-z_]+)/(?P<pk>[0-9]+)/update_variant$', views.ProductVariantUpdate.as_view()),
    url(r'^orders/shopify/(?P<pk>[0-9]+)$', views.ShopifyOrderDetail.as_view()),
    url(r'^orders/(?P<store_type>[a-z_]+)/(?P<pk>[0-9]+)/add_note$', views.OrderNotesUpdate.as_view()),
    url(r'^sub_user_emails$', views.SubUserEmails.as_view()),
]
