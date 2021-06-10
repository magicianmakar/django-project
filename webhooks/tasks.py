from django.contrib.auth.models import User
from django.conf import settings

from app.celery_base import celery_app, CaptureFailure
from metrics.activecampaign import ActiveCampaignAPI


@celery_app.task(base=CaptureFailure, ignore_result=True)
def setup_free_account(user_id):
    user = User.objects.get(id=user_id)
    phone = user.get_config('_phone')

    if settings.ACTIVECAMPAIGN_KEY and phone:
        api = ActiveCampaignAPI()
        api.get_or_create_contact(user.email, {'phone': phone})
