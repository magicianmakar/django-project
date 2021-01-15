from django.urls import path

import offers.views

app_name = 'offers'

urlpatterns = [
    path('<int:seller_id>/<int:pk>/<slug:slug>', offers.views.OfferDetailView.as_view(), name='details'),
    path('subscribe/<int:seller_id>/<int:pk>', offers.views.SubscribeView.as_view(), name='subscribe'),
]
