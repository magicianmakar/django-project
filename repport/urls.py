from django.conf.urls import patterns, include, url

import repport.views

urlpatterns = patterns('',
    url(r'^$', repport.views.index, name='index'),
    url(r'^logout$', repport.views.logout),

    url(r'^project/(?P<project_id>[0-9]+)$', repport.views.project_view),
    url(r'^category/(?P<cat_id>[0-9]+)$', repport.views.category_view),
    url(r'^topic/(?P<topic_id>[0-9]+)$', repport.views.topic_view),
    url(r'^topic/(?P<topic_id>[0-9]+)$', repport.views.topic_view),

    url(r'^project/scorecard/(?P<project_id>[0-9]+)$', repport.views.scorecard_view),
    url(r'^project/preview/(?P<project_id>[0-9]+)$', repport.views.preview_project),
    url(r'^project/pdf/(?P<project_id>[0-9]+)$$', repport.views.generate_pdf),
    url(r'^project/templates/(?P<project_id>[0-9]+)$$', repport.views.project_templates),
    url(r'^project/metrics/(?P<project_id>[0-9]+)$$', repport.views.project_metrics),

    url(r'^api/(?P<target>[a-z-]+)$', repport.views.api),

    url(r'^accounts/register$', repport.views.register, name='register'),
)
