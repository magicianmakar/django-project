import requests

from django.conf import settings

from lib.exceptions import capture_exception
from shopified_core.utils import http_response_extra

from . import settings as app_settings


def create_fp_user(user):
    # Add user to First Promoter
    compain_conf = {}
    if not user.profile.plan.is_free:
        compain_conf['campaign_id'] = app_settings.FIRST_PROMOTER_PRO_CAMPAIGN_ID

    rep = requests.post(
        'https://firstpromoter.com/api/v1/promoters/create',
        json={
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'website': settings.APP_URL,
            'custom_field': {
                'user_id': user.id,
            },
            **compain_conf,
        },
        headers={
            'x-api-key': app_settings.FIRST_PROMOTER_API_KEY,
        }
    )

    try:
        rep.raise_for_status()
    except:
        capture_exception(extra=http_response_extra(rep))

    return rep.ok


def upgrade_fp_user(user, promoter_id):
    # Add user to First Promoter
    rep = requests.post(
        'https://firstpromoter.com/api/v1/promoters/move_to_campaign',
        json={
            'id': promoter_id,
            'destination_campaign_id': app_settings.FIRST_PROMOTER_PRO_CAMPAIGN_ID,
        },
        headers={
            'x-api-key': app_settings.FIRST_PROMOTER_API_KEY,
        }
    )

    try:
        rep.raise_for_status()
    except:
        capture_exception(extra=http_response_extra(rep))

    return rep.ok


def find_fp_user(user):
    rep = requests.get(
        url='https://firstpromoter.com/api/v1/promoters/show',
        params={'promoter_email': user.email},
        headers={'x-api-key': app_settings.FIRST_PROMOTER_API_KEY}
    )

    try:
        rep.raise_for_status()
    except:
        capture_exception(extra=http_response_extra(rep))

    if rep.ok:
        return rep.json()
