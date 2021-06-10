from django.contrib.auth.models import User
from django.conf import settings

from app.celery_base import celery_app, CaptureFailure
from leadgalaxy.models import GroupPlan
from metrics.activecampaign import ActiveCampaignAPI


@celery_app.task(base=CaptureFailure, ignore_result=True)
def setup_free_account(user_id):
    user = User.objects.get(id=user_id)
    phone = user.get_config('__phone')

    if user.get_config('__plan'):
        free_plan = GroupPlan.objects.get(id=user.get_config('__plan'))
        if user.profile.plan != free_plan and user.profile.plan.free_plan:
            user.profile.change_plan(free_plan)

    if settings.ACTIVECAMPAIGN_KEY and phone:
        api = ActiveCampaignAPI()
        api.get_or_create_contact(user.email, {'phone': phone})
