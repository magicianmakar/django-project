from django.conf.urls import url

import shopified_core.views

urlpatterns = [
    url(r'^api/(v(?P<version>[0-9])/)?((?P<store_type>[a-z_-]+)/)?(?P<target>[a-z_-]+)$',
        shopified_core.views.ShopifiedApiBase.as_view()),
]
