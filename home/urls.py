from django.conf.urls import url

import home.views

urlpatterns = [
    url(r'^(?:settings)?$', home.views.home_page_view, name='index'),
]
