from requests.exceptions import HTTPError

from django.contrib.auth.models import User

from app.celery_base import CaptureFailure, celery_app
from lib.exceptions import capture_exception, capture_message

from .utils import SureDoneAdminUtils, SureDonePusher, SureDoneUtils


@celery_app.task(base=CaptureFailure)
def register_new_sd_user(pusher_channel, user_id):
    user = User.objects.get(id=user_id)
    result = SureDoneAdminUtils().register_new_user(user)
    sd_account = result.get('account')
    pusher = SureDonePusher(pusher_channel)
    default_event = 'sd-config-setup'

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
    try:
        user = User.objects.get(id=user_id)

        sd_utils = SureDoneUtils(user, account_id=sd_account_id)
        all_options_data = sd_utils.api.get_all_account_options()

        # Set up custom fields
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

        # Set up custom fields for variants
        failed_variant_fields = sd_utils.sd_account.verify_variation_fields(all_options_data)
        if failed_variant_fields:
            request_data = {'site_cart_variants_set': failed_variant_fields}

            tries_left = 3
            success = False
            while tries_left > 0 and not success:
                api_resp = sd_utils.api.update_user_settings(request_data)
                try:
                    api_resp_data = api_resp.json()

                    error_messages = api_resp_data.get('errors', {}).get('site_cart_variants_set')
                    if api_resp_data.get('result') != 'success' or error_messages:
                        capture_message('Request to set custom fields variations failed.', extra={
                            'suredone_account_id': sd_account_id,
                            'response_code': api_resp.status_code,
                            'response_reason': api_resp.reason,
                            'response_data': api_resp_data,
                            'failed_variant_fields': failed_variant_fields,
                        })
                    else:
                        success = True
                        break
                except Exception:
                    capture_exception(extra={
                        'description': 'API error when trying to set custom field variants.',
                        'suredone_account_id': sd_account_id,
                        'response_code': api_resp.status_code,
                        'response_reason': api_resp.reason,
                        'failed_variant_fields': failed_variant_fields
                    })
                tries_left -= 1

        # Verify facebook fields mapping
        missing_fields_per_store = sd_utils.sd_account.verify_fb_fields_mapping(all_options_data)
        request_data = {'plugin_settings': [
            {
                'name': 'facebook',
                'instance': key,
                'set': 'custom_field_mappings',
                'value': value,
            } for key, value in missing_fields_per_store.items()
        ]}
        api_resp = sd_utils.api.update_plugin_settings(request_data)
        try:
            api_resp.raise_for_status()
        except HTTPError:
            capture_exception(extra={
                'description': 'API error when trying to set facebook fields mapping.',
                'suredone_account_id': sd_account_id,
                'response_code': api_resp.status_code,
                'response_reason': api_resp.reason,
                'failed_variant_fields': failed_variant_fields
            })

    except:
        capture_exception(extra={
            'description': 'Failed to configure_user_custom_fields',
            'suredone_account_id': sd_account_id,
        })
