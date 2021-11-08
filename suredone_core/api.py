import json
import requests

from django.conf import settings

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

    def delete_products_bulk(self, guids_to_delete: list):
        return self.handle_bulk_api('delete', guids_to_delete)

    def get_all_account_options(self):
        url = f'{self.API_ENDPOINT}/v1/options/all'

        response = requests.get(url, headers=self.HEADERS)
        if response.ok:
            try:
                return response.json()
            except ValueError:
                pass
        else:
            pass

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
