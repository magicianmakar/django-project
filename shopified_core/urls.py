from django.conf.urls import url

import shopified_core.views

urlpatterns = [
    url(r'^api/(v(?P<version>[0-9])/)?((?P<store_type>[a-z]+)/)?(?P<target>[a-z-]+)$',
        shopified_core.views.ShopifiedApi.as_view()),
]
