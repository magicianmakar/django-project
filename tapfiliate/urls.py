from django.conf.urls import url

import tapfiliate.views

urlpatterns = [
    url(r'^conversion$', tapfiliate.views.conversion, name='tapfiliate.views.conversion')
]
