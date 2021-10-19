from django.contrib.auth.models import User

from app.celery_base import CaptureFailure, celery_app
from lib.exceptions import capture_message

from .utils import SureDoneAdminUtils, SureDonePusher, SureDoneUtils


@celery_app.task(base=CaptureFailure)
def register_new_sd_user(pusher_channel, user_id):
    user = User.objects.get(id=user_id)
    result = SureDoneAdminUtils().register_new_user(user)
    sd_account = result.get('account')
    pusher = SureDonePusher(pusher_channel)
    default_event = 'ebay-config-setup'

    if result.get('error') or sd_account is None:
        capture_message('Error creating a new account.', extra={'error_message': result.get('error')})
        pusher.trigger(default_event, {
            'success': False,
            'error': 'Something went wrong. Please try again or contact support.'
        })
        return

    pusher.trigger(default_event, {'success': True})

    return sd_account.id


@celery_app.task(base=CaptureFailure)
def configure_user_custom_fields(sd_account_id, user_id):
    user = User.objects.get(id=user_id)

    sd_utils = SureDoneUtils(user, account_id=sd_account_id)
    all_options_data = sd_utils.api.get_all_account_options()

    failed_set_api_resp = {}
    missing_fields = sd_utils.sd_account.verify_custom_fields_created(all_options_data)
    for i, fields_set in enumerate(missing_fields):
        tries_left = 3
        success = False
        request_data = {f'user_field_names_add{k}': v for k, v in fields_set.items()}
        request_data['user_field_names_addbulk'] = True

        api_resp = {}
        while tries_left > 0:
            api_resp = sd_utils.api.update_settings(request_data)
            if isinstance(api_resp, dict) and api_resp.get('result') == 'success':
                success = True
                break
            tries_left -= 1

        if not success:
            failed_set_api_resp[i] = api_resp

    if failed_set_api_resp:
        capture_message('Request to configure SureDone user custom fields failed.', extra={
            'user_id': user_id,
            'suredone_account_id': sd_account_id,
            'missing_fields': missing_fields,
            'result_per_set': failed_set_api_resp
        })
