from django.conf.urls import url

import multichannel_products_core.views

urlpatterns = [
    url(r'^products/?(?P<tpl>(grid|table))?$', multichannel_products_core.views.ProductsList.as_view(),
        name='products_list'),
    url(r'^product/(?P<pk>[0-9]+)$', multichannel_products_core.views.ProductDetailView.as_view(),
        name='product_detail'),
    url(r'^product/mapping/(?P<pk>[0-9]+)$', multichannel_products_core.views.VariantsMappingView.as_view(),
        name='variants_mapping'),
    url(r'^templates$', multichannel_products_core.views.TemplatesList.as_view(),
        name='templates_list'),
]
