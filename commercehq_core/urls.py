from django.conf.urls import patterns, url

import commercehq_core.views

urlpatterns = patterns(
    '',
    url(r'^api/(?P<target>[a-z-]+)$', commercehq_core.views.api),
    url(r'^$', commercehq_core.views.index_view, name='index'),
)
