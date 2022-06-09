import json
import requests

from django.conf import settings

from lib.exceptions import capture_exception
from suredone_core.models import SureDoneAccount
from suredone_core.param_encoder import param


class SureDoneApiHandler:
    API_ENDPOINT = 'https://api.suredone.com'
    API_EDITOR_PATH = '/v1/editor/items'

    def __init__(self, api_username: str, api_token: str, version=None):
        self.api_username = api_username
        self.api_token = api_token
        self.version = version
        self.HEADERS = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Auth-User': api_username,
            'X-Auth-Token': api_token,
            'X-Auth-Integration': settings.SUREDONE_PARTNER_API_NAME
        }

    def validate_store_data(self, data):
        title = data.get('title', '')
        api_username = data.get('api_username', '')
        api_token = data.get('api_token', '')

        error_messages = []

        if len(title) > SureDoneAccount._meta.get_field('title').max_length:
            error_messages.append('Title is too long.')
        if len(api_username) > SureDoneAccount._meta.get_field('api_username').max_length:
            error_messages.append('SureDone username is too long')
        if len(api_token) > SureDoneAccount._meta.get_field('api_token').max_length:
            error_messages.append('SureDone token is too long')

        if not api_username:
            error_messages.append('API username is required')

        if not api_token:
            error_messages.append('API token is required')

        return error_messages

    def refresh_ebay_profiles(self, instance_id: int):
        url = f'{self.API_ENDPOINT}/v3/internal/ebay/refresh-profiles'
        params = {'instance': instance_id}

        return requests.get(url, params=params, headers=self.HEADERS)

    def authorize_channel_v1(self, request_data: dict):
        url = f'{self.API_ENDPOINT}/v1/authorize'
        data = param(request_data)

        response = requests.post(url, data=data, headers=self.HEADERS)

        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            pass

    def authorize_channel_v3(self, request_data: dict, legacy=False):
        url = f'{self.API_ENDPOINT}/v3/authorize/ebay/url'
        if legacy:
            request_data['legacy'] = True

        response = requests.get(url, params=request_data, headers=self.HEADERS)

        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            try:
                return response.json()
            except ValueError:
                pass

    def authorize_ebay_channel(self, request_data: dict, legacy=False):
        url = f'{self.API_ENDPOINT}/v3/authorize/ebay/url'
        if legacy:
            request_data['legacy'] = True

        return requests.get(url, params=request_data, headers=self.HEADERS)

    def authorize_ebay_complete(self, code: str, state: str):
        url = f'{self.API_ENDPOINT}/v3/authorize/ebay/complete'
        data = {'code': code, 'state': state}

        response = requests.post(url, data=data, headers=self.HEADERS)

        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            try:
                return response.json()
            except ValueError:
                pass

    def authorize_ebay_complete_legacy(self):
        url = f'{self.API_ENDPOINT}/v3/authorize/ebay/complete'
        data = {'legacy': True}

        response = requests.post(url, data=data, headers=self.HEADERS)

        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            try:
                return response.json()
            except ValueError:
                pass

    def update_settings(self, request_data: dict):
        url = f'{self.API_ENDPOINT}/v1/settings'
        data = param(request_data)

        response = requests.post(url, data=data, headers=self.HEADERS)

        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            pass

    def update_user_settings(self, request_data: dict):
        url = f'{self.API_ENDPOINT}/v1/settings'
        data = param(request_data)

        return requests.post(url, data=data, headers=self.HEADERS)

    def add_new_ebay_instance(self):
        url = f'{self.API_ENDPOINT}/v1/settings'
        data = param({'ebay_instance_add': 'on'})

        return requests.post(url, data=data, headers=self.HEADERS)

    def get_fb_channel_auth_url(self, instance_id):
        url = f'{self.API_ENDPOINT}/v3/authorize/facebook/url'
        request_data = {'instance': instance_id}

        return requests.get(url, params=request_data, headers=self.HEADERS)

    def post_fb_onboard_instance(self, cms_id: str, instance_id: int):
        url = f'{self.API_ENDPOINT}/v3/authorize/facebook/onboard'
        data = param({
            'cms_id': cms_id,
            'instance': instance_id,
        })

        return requests.post(url, data=data, headers=self.HEADERS)

    def add_new_fb_instance(self, instance_id: int):
        url = f'{self.API_ENDPOINT}/v3/authorize/facebook/create'
        data = param({'instance': instance_id})

        return requests.post(url, data=data, headers=self.HEADERS)

    def remove_fb_channel_auth(self, instance_id):
        url = f'{self.API_ENDPOINT}/v3/authorize/facebook/revoke'
        request_data = {'instance': instance_id}

        return requests.get(url, params=request_data, headers=self.HEADERS)

    def authorize_fb_complete(self, instance, code, granted_scopes, denied_scopes, state):
        url = f'{self.API_ENDPOINT}/v3/authorize/facebook/complete'
        data = param({
            'instance': instance,
            'code': code,
            'granted_scopes': granted_scopes,
            'denied_scopes': denied_scopes,
            'state': state,
        })

        return requests.post(url, data=data, headers=self.HEADERS)

    def get_products(self, params=None):
        url = f'{self.API_ENDPOINT}{self.API_EDITOR_PATH}'

        response = requests.get(url, params=params, headers=self.HEADERS)
        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            pass

    def search_ebay_categories(self, store_index: int, search_term: str):
        url = f'{self.API_ENDPOINT}{self.API_EDITOR_PATH}'

        params = {
            'ebay-category-search': search_term,
            'instanceid': store_index,
        }

        response = requests.get(url, params=params, headers=self.HEADERS)
        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            pass

    def get_ebay_specifics(self, site_id: int, cat_id: int):
        url = f'{self.API_ENDPOINT}{self.API_EDITOR_PATH}'
        params = {
            'ebay-specifics-category-id': cat_id,
            'ebay-site-id': site_id
        }

        response = requests.get(url, params=params, headers=self.HEADERS)
        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            pass

    def search_fb_categories(self, search_term: str):
        url = f'{self.API_ENDPOINT}/v1/internal/facebook/categories'
        params = {'search': search_term}

        response = requests.get(url, params=params, headers=self.HEADERS)
        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            pass

    def get_item_by_guid(self, guid):
        url = f'{self.API_ENDPOINT}{self.API_EDITOR_PATH}/edit'
        params = {
            'guid': guid,
        }

        response = requests.get(url, params=params, headers=self.HEADERS)
        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            pass

    def handle_bulk_api(self, action: str, variations_data: list, skip_all_channels=False):
        url = f'{self.API_ENDPOINT}{self.API_EDITOR_PATH}'
        params = {'syncskip': 1} if skip_all_channels else {}

        # Insert the action type to the request data
        variations_data[0].insert(0, f'action={action}')
        for i in range(1, len(variations_data)):
            variations_data[i].insert(0, '')

        data = param({
            'requests': variations_data
        })

        response = requests.post(url, data=data, params=params, headers=self.HEADERS)
        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            pass

    def relist_product_details_bulk(self, variations_data: list, skip_all_channels=False):
        return self.handle_bulk_api('relist', variations_data, skip_all_channels)

    def edit_product_details_bulk(self, variations_data: list, skip_all_channels=False):
        return self.handle_bulk_api('edit', variations_data, skip_all_channels)

    def add_products_bulk(self, variations_data: list, skip_all_channels=False):
        return self.handle_bulk_api('add', variations_data, skip_all_channels)

    def delete_products_bulk(self, guids_to_delete: list, skip_all_channels=False):
        return self.handle_bulk_api('delete', guids_to_delete, skip_all_channels)

    def get_all_account_options(self, option_type: str = None):
        url = f'{self.API_ENDPOINT}/v1/options/{option_type if option_type else "all"}'
        try:
            response = requests.get(url, headers=self.HEADERS, timeout=25)
            if response.ok:
                try:
                    return response.json()
                except ValueError:
                    pass
            else:
                pass
        except(requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout):
            capture_exception(extra={
                'description': 'Timeout exception when requesting SureDone user options',
                'suredone_account_username': self.HEADERS['X-Auth-User'],
            })

    def get_platform_statuses(self):
        url = f'{self.API_ENDPOINT}/v3/channel/statuses'

        return requests.get(url, headers=self.HEADERS)

    def get_orders(self, params=None):
        url = f'{self.API_ENDPOINT}/v3/orders'

        response = requests.get(url, params=params, headers=self.HEADERS)
        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            pass

    def get_order_details(self, order_id: int):
        url = f'{self.API_ENDPOINT}/v3/orders/{order_id}'

        response = requests.get(url, headers=self.HEADERS)
        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            pass

    def update_order_details(self, oid: int, order_details: dict, params=None):
        url = f'{self.API_ENDPOINT}/v3/orders/{oid}'
        api_data = json.dumps(order_details)
        headers = {**self.HEADERS, 'Content-Type': 'multipart/x-www-form-urlencoded'}

        return requests.patch(url, data=api_data, params=params, headers=headers)

    def update_plugin_settings(self, data: dict):
        url = f'{self.API_ENDPOINT}/v1/settings/plugins'
        return requests.post(url, data=param(data), headers=self.HEADERS)

    def update_plugin_settings_json(self, data: dict):
        url = f'{self.API_ENDPOINT}/v1/settings'
        headers = {**self.HEADERS, 'Content-Type': 'Application/json'}

        return requests.post(url, json=data, headers=headers)

    def get_import_options(self, store_prefix: str):
        url = f'{self.API_ENDPOINT}/v1/options/{store_prefix}_attribute_mapping'

        return requests.get(url, headers=self.HEADERS)

    def get_import_file_download_link(self, filename: str):
        url = f'{self.API_ENDPOINT}/v1/bulk/imports/{filename}'

        return requests.get(url, headers=self.HEADERS)

    def post_new_ebay_products_import_job(self, store_prefix: str):
        url = f'{self.API_ENDPOINT}/v1/settings'
        data = param({
            f'{store_prefix}_import': 'true',
            f'{store_prefix}_import_fileonly': 'true',
            f'{store_prefix}_import_action': 'match',
            f'{store_prefix}_import_email': 'suredone@universium.co',
        })
        return requests.post(url, data=data, headers=self.HEADERS)

    def post_imported_products(self, bulk_data: list, skip_all_channels=True):
        url = f'{self.API_ENDPOINT}{self.API_EDITOR_PATH}'
        params = {'force': 'true'}
        if skip_all_channels:
            params['syncskip'] = 1

        data = param({
            'requests': bulk_data
        })

        return requests.post(url, data=data, params=params, headers=self.HEADERS)


class SureDoneAdminApiHandler:
    API_ENDPOINT = 'https://api.suredone.com'
    HEADERS = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Auth-User': settings.SUREDONE_PARTNER_API_USERNAME,
        'X-Auth-Token': settings.SUREDONE_PARTNER_API_TOKEN,
        'X-Auth-Integration': settings.SUREDONE_PARTNER_API_NAME
    }

    @classmethod
    def register_user(cls, username: str, email: str, password: str):
        url = f'{cls.API_ENDPOINT}/v1/register'

        data = {
            'user': username,
            'email': email,
            'password': password
        }

        return requests.post(url, data=data, headers=cls.HEADERS)

    @classmethod
    def list_all_users(cls):
        url = f'{cls.API_ENDPOINT}/v1/profile/users'

        response = requests.get(url, headers=cls.HEADERS)

        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            pass

    @classmethod
    def authorize_user(cls, username: str, password: str):
        url = f'{cls.API_ENDPOINT}/v1/auth'

        data = {
            'user': username,
            'pass': password
        }

        return requests.post(url, data=data, headers=cls.HEADERS)
