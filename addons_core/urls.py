from django.urls import path

import addons_core.views

urlpatterns = [
    path('', addons_core.views.AddonsListView.as_view(), name='addons.list_view'),
    path('<slug:slug>', addons_core.views.AddonsDetailsView.as_view(), name='addons.details_view'),
    path('edit/<slug>', addons_core.views.AddonsEditView.as_view(), name='addons.edit_view'),
    path('category/<slug>', addons_core.views.CategoryListView.as_view(), name='addons.category_view'),
]
