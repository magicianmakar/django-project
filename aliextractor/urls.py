from django.conf.urls import url

import aliextractor.views

urlpatterns = [
    url(r'^$', aliextractor.views.index, name='aliextractor_index'),

]
