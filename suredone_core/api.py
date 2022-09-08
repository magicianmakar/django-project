import json
import requests
from copy import deepcopy

from django.conf import settings

from lib.exceptions import capture_exception
from shopified_core.utils import cached_return, safe_float
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
            new_token = self.handle_invalid_token_error(response)
            if new_token:
                self.HEADERS['X-Auth-Token'] = new_token
                return self.authorize_channel_v1(request_data)
            else:
                return {"result": "error", "message": "Something went wrong, please try again."}

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
            new_token = self.handle_invalid_token_error(response)
            if new_token:
                self.HEADERS['X-Auth-Token'] = new_token
                return self.authorize_channel_v3(request_data, legacy)
            else:
                return {"result": "error", "message": "Something went wrong, please try again."}

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
            new_token = self.handle_invalid_token_error(response)
            if new_token:
                self.HEADERS['X-Auth-Token'] = new_token
                return self.authorize_ebay_complete(code, state)
            else:
                return {"result": "error", "message": "Something went wrong, please try again."}

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
            new_token = self.handle_invalid_token_error(response)
            if new_token:
                self.HEADERS['X-Auth-Token'] = new_token
                return self.authorize_ebay_complete_legacy()
            else:
                return {"result": "error", "message": "Something went wrong, please try again."}

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
            new_token = self.handle_invalid_token_error(response)
            if new_token:
                self.HEADERS['X-Auth-Token'] = new_token
                return self.update_settings(request_data)
            else:
                return {"result": "error", "message": "Something went wrong, please try again."}

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
        headers = {**self.HEADERS, 'Content-Type': 'Application/json'}
        request_data = {'instance': instance_id}

        response = requests.post(url, json=request_data, headers=headers)
        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            pass

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

    def get_google_channel_auth_url(self, instance_id):
        url = f'{self.API_ENDPOINT}/v3/authorize/google/url'
        request_data = {'instance': instance_id}

        return requests.get(url, params=request_data, headers=self.HEADERS)

    def post_google_onboard_instance(self, cms_id: str, instance_id: int):
        url = f'{self.API_ENDPOINT}/v3/authorize/google/onboard'
        data = param({
            'cms_id': cms_id,
            'instance': instance_id,
        })

        return requests.post(url, data=data, headers=self.HEADERS)

    def add_new_google_instance(self, instance_id: int):
        url = f'{self.API_ENDPOINT}/v3/authorize/google/create'
        data = param({'instance': instance_id})

        return requests.post(url, data=data, headers=self.HEADERS)

    def remove_google_channel_auth(self, instance_id):
        url = f'{self.API_ENDPOINT}/v3/authorize/google/revoke'
        headers = {**self.HEADERS, 'Content-Type': 'Application/json'}
        request_data = {'instance': instance_id}

        response = requests.post(url, json=request_data, headers=headers)
        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            pass

    def authorize_google_complete(self, instance, code, granted_scopes, denied_scopes, state):
        url = f'{self.API_ENDPOINT}/v3/authorize/google/complete'
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
            new_token = self.handle_invalid_token_error(response)
            if new_token:
                self.HEADERS['X-Auth-Token'] = new_token
                return self.get_products(params)
            else:
                return {"result": "error", "message": "Something went wrong, please try again."}

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
            new_token = self.handle_invalid_token_error(response)
            if new_token:
                self.HEADERS['X-Auth-Token'] = new_token
                return self.search_ebay_categories(store_index, search_term)
            else:
                return {"result": "error", "message": "Something went wrong, please try again."}

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
            new_token = self.handle_invalid_token_error(response)
            if new_token:
                self.HEADERS['X-Auth-Token'] = new_token
                return self.get_ebay_specifics(site_id, cat_id)
            else:
                return {"result": "error", "message": "Something went wrong, please try again."}

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
            new_token = self.handle_invalid_token_error(response)
            if new_token:
                self.HEADERS['X-Auth-Token'] = new_token
                return self.search_fb_categories(search_term)
            else:
                return {"result": "error", "message": "Something went wrong, please try again."}

    def search_google_categories(self, search_term: str):
        url = f'{self.API_ENDPOINT}/v1/internal/google/categories'
        params = {'search': search_term}

        response = requests.get(url, params=params, headers=self.HEADERS)

        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            new_token = self.handle_invalid_token_error(response)
            if new_token:
                self.HEADERS['X-Auth-Token'] = new_token
                return self.search_google_categories(search_term)
            else:
                return {"result": "error", "message": "Something went wrong, please try again."}

    def get_item_by_guid(self, guid, convert_prices_from_suredone=False):
        url = f'{self.API_ENDPOINT}{self.API_EDITOR_PATH}/edit'
        params = {
            'guid': guid,
        }

        response = requests.get(url, params=params, headers=self.HEADERS)

        if response.ok:
            try:
                response = response.json()

                if convert_prices_from_suredone:
                    # Transform SureDone format of prices to Dropified format
                    if safe_float(response.get('discountprice')):
                        response['price'] = response.get('discountprice')
                    if response.get('attributes'):
                        for variant_index in range(len(response.get('attributes'))):
                            discountprice = response.get('attributes').get(f'{variant_index + 1}', {}).get('discountprice')
                            if safe_float(discountprice):
                                response['attributes'][f'{variant_index + 1}']['price'] = discountprice

                return response
            except ValueError:
                pass
        else:
            new_token = self.handle_invalid_token_error(response)
            if new_token:
                self.HEADERS['X-Auth-Token'] = new_token
                return self.get_item_by_guid(guid)
            else:
                return {"result": "error", "message": "Something went wrong, please try again."}

    def handle_bulk_api(self, action: str, variations_data: list, skip_all_channels=False, force=False):
        url = f'{self.API_ENDPOINT}{self.API_EDITOR_PATH}'
        params = {}

        if skip_all_channels:
            params['skip_all_channels'] = 1
        if force:
            params['force'] = 'true'

        request_data = deepcopy(variations_data)
        # Insert the action type to the request data
        request_data[0].insert(0, f'action={action}')
        for i in range(1, len(request_data)):
            request_data[i].insert(0, '')

        data = param({
            'requests': request_data
        })

        response = requests.post(url, data=data, params=params, headers=self.HEADERS)

        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            new_token = self.handle_invalid_token_error(response)
            if new_token:
                self.HEADERS['X-Auth-Token'] = new_token
                return self.handle_bulk_api(action, variations_data, skip_all_channels)
            else:
                return {"result": "error", "message": "Something went wrong, please try again."}

    def relist_product_details_bulk(self, variations_data: list, skip_all_channels=False):
        return self.handle_bulk_api('relist', variations_data, skip_all_channels)

    def edit_product_details_bulk(self, variations_data: list, skip_all_channels=False, force=False):
        return self.handle_bulk_api('edit', variations_data, skip_all_channels, force)

    def add_products_bulk(self, variations_data: list, skip_all_channels=False):
        return self.handle_bulk_api('add', variations_data, skip_all_channels)

    def end_product_details_bulk(self, variations_data: list, skip_all_channels=False):
        return self.handle_bulk_api('end', variations_data, skip_all_channels)

    def delete_products_bulk(self, guids_to_delete: list, skip_all_channels=False):
        return self.handle_bulk_api('delete', guids_to_delete, skip_all_channels)

    def __get_all_account_options(self, option_type: str = None):
        url = f'{self.API_ENDPOINT}/v1/options/{option_type if option_type else "all"}'
        try:
            response = requests.get(url, headers=self.HEADERS, timeout=25)

            if response.ok:
                try:
                    return response.json()
                except ValueError:
                    pass
            else:
                new_token = self.handle_invalid_token_error(response)
                if new_token:
                    self.HEADERS['X-Auth-Token'] = new_token
                    return self.get_all_account_options(option_type)
                else:
                    return {"result": "error", "message": "Something went wrong, please try again."}
        except(requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout):
            capture_exception(extra={
                'description': 'Timeout exception when requesting SureDone user options',
                'suredone_account_username': self.HEADERS['X-Auth-User'],
            })

    def get_all_account_options(self, option_type: str = None):
        cached_func = cached_return(self.__get_all_account_options, user=self.HEADERS['X-Auth-User'])
        return cached_func(option_type)

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
            new_token = self.handle_invalid_token_error(response)
            if new_token:
                self.HEADERS['X-Auth-Token'] = new_token
                return self.get_orders(params)
            else:
                return {"result": "error", "message": "Something went wrong, please try again."}

    def get_logs(self, params=None):
        url = f'{self.API_ENDPOINT}/v3/logs'

        response = requests.post(url, params=params, headers=self.HEADERS)
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
            new_token = self.handle_invalid_token_error(response)
            if new_token:
                self.HEADERS['X-Auth-Token'] = new_token
                return self.get_order_details(order_id)
            else:
                return {"result": "error", "message": "Something went wrong, please try again."}

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
        # Use force to set the eBay source ID on the product
        # SureDone otherwise rejects ebay product ID as it's a read-only field
        params = {'force': 'true'}
        if skip_all_channels:
            params['syncskip'] = 1

        data = param({
            'requests': bulk_data
        })

        return requests.post(url, data=data, params=params, headers=self.HEADERS)

    def handle_invalid_token_error(self, response):
        try:
            result = response.json()
            if result.get('result') == 'error' and result.get('message') == 'Invalid Token':
                sd_user_account = SureDoneAccount.objects.get(api_username=self.api_username)
                sd_password = sd_user_account.password
                # re-authorize user
                api_resp = SureDoneAdminApiHandler.authorize_user(username=self.api_username, password=sd_password)
                api_resp.raise_for_status()
                user_data = api_resp.json()
                if user_data.get('result') == 'success':
                    sd_user_account.api_token = user_data.get('token')
                    sd_user_account.save()
                    return user_data.get('token')
        except Exception as e:
            capture_exception(extra={
                'description': 'Exception when handling invalid token error',
                'suredone_account_username': self.HEADERS['X-Auth-User'],
                'exception': e,
            })

    def get_last_log(self, identifier: str, context: str, action: str):
        url = f'{self.API_ENDPOINT}/v3/logs'
        headers = {**self.HEADERS, 'Content-Type': 'Application/json'}
        data = {
            'identifier': identifier,
            'context': context,
            'action': action,
            'records': 1,
            'sort': 'created_at:desc',
        }

        response = requests.post(url, json=data, headers=headers)
        if response.ok:
            try:
                logs = response.json().get('results', {}).get('logs', [])
                if logs:
                    return logs[0]
            except ValueError:
                pass


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
