from django.contrib.auth.models import User

from lib.exceptions import capture_exception

from app.celery_base import celery_app, CaptureFailure
from .utils import update_contact


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=30)
def update_hubspot_user(self, user_id):

    try:
        update_contact(User.objects.get(id=user_id))
    except:
        capture_exception()
