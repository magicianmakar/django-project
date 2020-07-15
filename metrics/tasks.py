from django.contrib.auth.models import User

from django.conf import settings
from app.celery_base import celery_app, CaptureFailure
from .activecampaign import ActiveCampaignAPI


@celery_app.task(base=CaptureFailure, ignore_result=True)
def activecampaign_update_plan(user_id):
    if not settings.ACTIVECAMPAIGN_KEY:
        return

    api = ActiveCampaignAPI()
    user = User.objects.get(id=user_id)
    try:
        user_exists = api.check_user_exists(user)
    except:
        user_exists = False

    if user_exists:
        contact_data = {
            'email': user.email,
            'custom_fields': api.get_user_plan_data(user)
        }
    else:
        contact_data = api.get_user_data(user)

    api.update_customer(contact_data, version='1')


@celery_app.task(base=CaptureFailure, ignore_result=True)
def activecampaign_update_store_count(user_id):
    if not settings.ACTIVECAMPAIGN_KEY:
        return

    api = ActiveCampaignAPI()
    user = User.objects.get(id=user_id)
    try:
        user_exists = api.check_user_exists(user)
    except:
        user_exists = False

    if user_exists:
        contact_data = {
            'email': user.email,
            'custom_fields': api.get_user_store_data(user)
        }
    else:
        contact_data = api.get_user_data(user)

    api.update_customer(contact_data, version='1')


@celery_app.task(base=CaptureFailure, ignore_result=True)
def activecampaign_update_email(from_email, to_email):
    if not settings.ACTIVECAMPAIGN_KEY:
        return

    api = ActiveCampaignAPI()
    api.update_user_email(from_email, to_email)


@celery_app.task(base=CaptureFailure, ignore_result=True)
def activecampaign_update_from_intercom(intercom_contact):
    if not settings.ACTIVECAMPAIGN_KEY:
        return

    acapi = ActiveCampaignAPI()
    contact = acapi.get_intercom_data(intercom_contact)
    acapi.update_customer(contact, version='1')
