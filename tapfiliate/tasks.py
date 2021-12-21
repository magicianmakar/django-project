

from app.celery_base import celery_app, CaptureFailure

from django.conf import settings

from lib.exceptions import capture_exception
from tapfiliate.utils import add_commission_from_stripe, add_successful_payment


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def commission_from_stripe(self, charge_id):
    if settings.TAPFILIATE_API_KEY:
        try:
            add_commission_from_stripe(charge_id)
        except:
            capture_exception()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def successful_payment(self, charge_id):
    if settings.TAPFILIATE_API_KEY:
        try:
            add_successful_payment(charge_id)
        except:
            capture_exception()
