from django.conf.urls import patterns, url

import shopify_revision.views

urlpatterns = patterns(
    '',
    url(r'^last$', shopify_revision.views.last,
        name='shopify_revision_last'),
)
