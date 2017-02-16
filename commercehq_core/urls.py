from django.conf.urls import patterns, url

import commercehq_core.views

urlpatterns = patterns(
    '',
    url(r'^$', commercehq_core.views.index_view, name='index'),
)
