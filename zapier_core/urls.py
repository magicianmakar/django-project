from django.conf.urls import include, url
from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.include_root_view = False

router.register(r'hooks', views.HookViewSet)
router.register(r'stores/shopify', views.ShopifyStoreViewSet, base_name='shopifystore')
router.register(r'stores/chq', views.CommerceHQStoreViewSet, base_name='commercehqstore')
router.register(r'products/shopify', views.ShopifyProductViewSet, base_name='shopifyproduct')
router.register(r'products/chq', views.CommerceHQProductViewSet, base_name='commercehqproduct')

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^product-alerts/$', views.ProductAlertList.as_view()),
    url(r'^product-changes/$', views.ProductChangesList.as_view()),
    url(r'^products/(?P<store_type>[a-z_]+)/(?P<pk>[0-9]+)/update_visibility$', views.ProductVisibilityUpdate.as_view()),
    url(r'^products/(?P<store_type>[a-z_]+)/(?P<pk>[0-9]+)/update_notes$', views.ProductNotesUpdate.as_view()),
    url(r'^products/(?P<store_type>[a-z_]+)/(?P<pk>[0-9]+)/update_variant$', views.ProductVariantUpdate.as_view()),
    url(r'^products/(?P<store_type>[a-z_]+)/(?P<pk>[0-9]+)/variants$', views.ProductVariantList.as_view()),
    url(r'^orders/shopify/$', views.ShopifyOrderList.as_view()),
    url(r'^order-tracks/shopify/$', views.ShopifyOrderTrackList.as_view()),
    url(r'^order-tracks/chq/$', views.CommerceHQOrderTrackList.as_view()),
    url(r'^orders/(?P<store_type>[a-z_]+)/(?P<pk>[0-9]+)$', views.OrderDetail.as_view()),
    url(r'^orders/(?P<store_type>[a-z_]+)/(?P<pk>[0-9]+)/add_note$', views.OrderNotesUpdate.as_view()),
    url(r'^sub_user_emails$', views.SubUserEmails.as_view()),
]
