from django.conf.urls import url

import fulfilment_fee.views

urlpatterns = [
    url(r'^fees-list$', fulfilment_fee.views.fees_list, name='fees_list'),
]
