from django.urls import path

import fp_affiliate.views

urlpatterns = [
    path('', fp_affiliate.views.IndexView.as_view(), name='fp_affiliate_index'),
]
