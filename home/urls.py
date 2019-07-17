from django.conf.urls import url

import home.views

urlpatterns = [
    url(r'^$', home.views.home_page_view, name='index'),
]
