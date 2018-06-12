from __future__ import absolute_import

from app.celery import celery_app, CaptureFailure

from raven.contrib.django.raven_compat.models import client as raven_client

from tapfiliate.utils import add_commission_from_stripe


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def commission_from_stripe(self, charge_id):
    try:
        add_commission_from_stripe(charge_id)
    except:
        raven_client.captureException()
