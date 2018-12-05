from django.conf.urls import url

import youtube_ads.views

urlpatterns = [
    url(r'^$', youtube_ads.views.index, name='youtube_ads.views.index'),
    url(r'^auth$', youtube_ads.views.auth, name='youtube_ads.views.auth'),
    url(r'^oauth2callback$', youtube_ads.views.oauth2callback, name='youtube_ads.views.oauth2callback'),
    url(r'^channels$', youtube_ads.views.channels, name='youtube_ads.views.channels'),
    url(r'^autocomplete$', youtube_ads.views.autocomplete, name='youtube_ads.views.autocomplete'),
    url(r'^lists$', youtube_ads.views.lists, name='youtube_ads.views.lists'),
    url(r'^lists/(?P<pk>[0-9]+)$', youtube_ads.views.list_detail, name='youtube_ads.views.list_detail'),
]
