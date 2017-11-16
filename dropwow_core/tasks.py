from __future__ import absolute_import

from app.celery import celery_app, CaptureFailure

from django.db.models import Q

from dropwow_core.utils import fulfill_dropwow_order
from dropwow_core.models import DropwowOrderStatus


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def fulfill_dropwow_items(self):
    dropwow_order_statuses = DropwowOrderStatus.objects.filter(Q(order_id='') | Q(order_id__isnull=True))
    for dropwow_order_status in dropwow_order_statuses:
        fulfill_dropwow_order(dropwow_order_status)
