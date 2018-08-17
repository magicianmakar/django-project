from django.conf.urls import url

import shopify_revision.views

urlpatterns = [
    url(r'^last$', shopify_revision.views.last,
        name='shopify_revision_last'),
]
