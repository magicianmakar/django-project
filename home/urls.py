from django.conf.urls import url

import home.views

urlpatterns = [
    url(r'^$', home.views.home_page_view, name='index'),
    url(r'^settings$', home.views.home_page_view, name='settings'),
    url(r'^goto/page/(?P<url_name>[a-zA-Z-_\.]+)$',
        home.views.GotoPage.as_view(),
        name='goto-page'),
]
