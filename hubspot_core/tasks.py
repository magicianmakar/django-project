from django.contrib.auth.models import User

from app.celery_base import celery_app, CaptureFailure
from lib.exceptions import capture_exception

from .utils import update_contact, update_plan_property_options


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=30)
def update_hubspot_user(self, user_id):

    try:
        update_contact(User.objects.get(id=user_id))
    except:
        pass


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=600)
def update_plans_list_in_hubspot(self):
    try:
        update_plan_property_options()
    except:
        capture_exception()
