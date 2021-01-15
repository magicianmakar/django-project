from django.urls import path

import addons_core.views

urlpatterns = [
    path('', addons_core.views.AddonsListView.as_view(), name='addons.list_view'),
    path('<int:pk>/<slug:slug>', addons_core.views.AddonsDetailsView.as_view(), name='addons.details_view'),
    path('category/<slug>', addons_core.views.CategoryListView.as_view(), name='addons.category_view'),
    path('my/addons', addons_core.views.MyAddonsListView.as_view(), name='myaddons'),
    path('upsell-install/<int:pk>/<slug:slug>', addons_core.views.UpsellInstall.as_view(), name='addons.upsell_install'),
    path('upsell-install-loggedin/<int:pk>/<slug:slug>', addons_core.views.UpsellInstallLoggedIn.as_view(), name='addons.upsell_install_loggedin'),
    path('shopify/subscribe/<int:pk>/<slug:slug>', addons_core.views.ShopifySubscriptionUpdated.as_view(), name='addons.shopify_subscription'),
]
