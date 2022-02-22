import arrow
import itertools
import json
import re
import uuid
from copy import deepcopy
from pusher import Pusher
from requests.exceptions import HTTPError
from tenacity import RetryError, retry, stop_after_attempt, wait_fixed
from typing import List
from unidecode import unidecode

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils.crypto import get_random_string

from lib.exceptions import capture_exception, capture_message
from shopified_core.shipping_helper import (
    country_from_code,
    fix_br_address,
    get_uk_province,
    province_from_code,
    support_other_in_province,
    valide_aliexpress_province
)
from shopified_core.utils import hash_url_filename, safe_int, safe_json, safe_str
from supplements.utils import supplement_customer_address

from .api import SureDoneAdminApiHandler, SureDoneApiHandler
from .models import InvalidSureDoneStoreInstanceId, SureDoneAccount

SUREDONE_DATE_FORMAT = 'YYYY-MM-DD HH:mm:ss'


def parse_suredone_date(date_str: str):
    global SUREDONE_DATE_FORMAT
    try:
        return arrow.get(date_str, SUREDONE_DATE_FORMAT)
    except ValueError:
        return None


class SureDoneUtils:
    SUREDONE_DATE_FORMAT = 'YYYY-MM-DD HH:mm:ss'

    def __init__(self, user, account_id=None):
        self.user = user
        self._reload_api(account_id)

    @property
    def api(self):
        if not hasattr(self, '_api') or self._api is None:
            self._reload_api()

        return self._api

    @property
    def account_stores_config(self):
        if not hasattr(self, '_account_stores_config'):
            self._reload_account_stores_config()
        return self._account_stores_config

    def _reload_api(self, account_id=None):
        self.sd_account = self.get_sd_account(self.user, account_id)
        if self.sd_account:
            self._api = self.get_sd_api(self.sd_account)
        else:
            self._api = None

    def _reload_account_stores_config(self):
        self._account_stores_config = {}

        # 1. Get all suredone options
        all_options_data = self.get_all_user_options()

        # 2. Extract a list of all channels
        if all_options_data:
            plugin_settings = safe_json(all_options_data.pop('plugin_settings', '{}'), {})

            # 2.1. Get a list of eBay and Amazon channels
            channel_info = plugin_settings.get('channel', {})
            self._account_stores_config = {
                'ebay': [1, *[safe_int(i.get('instanceId')) for i in channel_info.get('ebay', {}).values()
                              if 'instanceId' in i]],
                'amzn': [1, *[safe_int(i.get('instanceId')) for i in channel_info.get('amazon', {}).values()
                              if 'instanceId' in i]],
            }

            # 2.2. Get a list of all other channel types
            register_data = plugin_settings.get('register', {})

            # 2.2.1. Facebook channels
            if 'facebook' in register_data.get('context', {}):
                facebook_instances = [1]
                addnl_fb_channels = list(register_data.get('instance', {}).get('facebook', {}).values())
                for channel in addnl_fb_channels:
                    instance_id = channel.get('instance')
                    if instance_id is not None and instance_id != '':
                        facebook_instances.append(instance_id)
                self._account_stores_config['facebook'] = facebook_instances

    def get_all_user_options(self, update_db=True, verify_custom_fields=False):
        all_options_data = self.api.get_all_account_options()

        if all_options_data and isinstance(all_options_data, dict):
            if update_db:
                self.sd_account.update_options_config(all_options_data, overwrite=True)
            if verify_custom_fields:
                failed_sets = self.sd_account.verify_custom_fields_created(all_options_data)
                failed_variant_fields = self.sd_account.verify_variation_fields(all_options_data)
                if failed_sets or failed_variant_fields:
                    from .tasks import configure_user_custom_fields
                    configure_user_custom_fields.apply_async(kwargs={
                        'sd_account_id': self.sd_account.id,
                        'user_id': self.user.id,
                    })

        return all_options_data

    def get_store_statuses_by_platform(self, platform=None):
        try:
            resp = self.api.get_platform_statuses()
            resp.raise_for_status()
        except HTTPError:
            return [] if platform else {}

        statuses = resp.json().get('results', {})
        return statuses.get(platform, []) if platform else statuses

    def get_skip_channels_config(self, channel_type: str, instance_id: int, skip_type: str = 'true',
                                 send_type: str = 'false'):
        skip_channels_config = {}

        for k, v in self.account_stores_config.items():
            skip_channels_config.update({
                f'{k}{"" if i == 1 else i}skip': skip_type for i in v if k != channel_type or i != instance_id
            })
        skip_channels_config[f'{channel_type}{"" if instance_id == 1 else instance_id}skip'] = send_type

        return skip_channels_config

    def get_sd_account(self, user, account_id=None):
        sd_account = None
        if account_id is not None:
            try:
                sd_account = SureDoneAccount.objects.get(id=account_id, user=user.models_user)
            except SureDoneAccount.DoesNotExist:
                sd_account = None
        elif user is not None:
            try:
                sd_account = SureDoneAccount.objects.filter(user=user.models_user).filter(is_active=True).first()
            except SureDoneAccount.DoesNotExist:
                sd_account = None

        return sd_account

    def get_sd_api(self, sd_account: SureDoneAccount):
        return SureDoneApiHandler(
            api_username=sd_account.api_username,
            api_token=sd_account.api_token)

    def parse_suredone_date(self, date_str: str):
        try:
            return arrow.get(date_str, self.SUREDONE_DATE_FORMAT)
        except ValueError:
            return None

    def get_all_products(self, filters=None, paginate=True, page=None, sort=None):
        """

        :param paginate:
        :type paginate:
        :param filters: formatted filters
        :type filters: str
        :param page:
        :type page:
        :param sort:
        :type sort:
        :return:
        :rtype:
        """
        if sort is None:
            sort = 'id_'
        if page is None:
            page = 1
        params = {'page': page, 'sort': sort}
        if filters:
            params.update({'q': filters})

        res = self.api.get_products(params)

        # the returned products should have "all" field with the number of products returned
        total_products_count = res.get('all', 0)

        # Extract products from the SD response,
        all_products = []
        for key in range(1, total_products_count + 1):
            product = res.get(f'{key}')
            if product:
                all_products.append(product)
            else:
                # TODO: test the breaking case
                break

        if not paginate and len(all_products) < total_products_count:
            api_page_count = 2

            while len(all_products) < total_products_count:
                params['page'] = api_page_count
                res = self.api.get_products(params)

                for key in range(1, total_products_count + 1):
                    product = res.get(f'{key}')
                    if product:
                        all_products.append(product)
                    else:
                        # TODO: test the breaking case
                        break
                api_page_count += 1

        return all_products

    def get_all_orders(self, filters=None, paginate=True, page=None, sort_by=None, sort_order=None):
        """
        Get all orders matching the passed filters

        :param paginate:
        :type paginate:
        :param filters: formatted filters
        :type filters: str
        :param page:
        :type page:
        :param sort_by:
        :type sort_by:
        :param sort_order:
        :type sort_order:
        :return:
        :rtype:
        """
        if page is None:
            page = 1
        if sort_by is None:
            sort_by = 'oid'
        if sort_order is None:
            sort_order = 'desc'
        params = {
            'page': page,
            'sort': sort_by,
            'sortorder': sort_order,
        }
        if filters:
            params.update({'q': filters})

        res = self.api.get_orders(params)

        # Returned products should have an "all" field with the number of products returned
        total_products_count = safe_int(res.get('count', 0))

        # Extract products from the SD response,
        all_orders = res.get('orders', [])

        return all_orders, total_products_count

    def format_filters(self, filter_map: dict) -> str:
        """
        A SureDone search filter formatting helper
        :param filter_map: a filter map dictionary in the following format:
            'field_name':
                'value': 'field_value',
                'relation': ':', ':-', ':>', ':<', ':=', etc. More info on searching:
                    https://support.suredone.com/support/solutions/articles/1000297038-searching-suredone
        :type filter_map: dict
        :return:
        :rtype:
        """
        query_elements = []
        for field, values in filter_map.items():
            relation = values.get('relation', ':=')
            value = values.get('value', '')
            query_elements.append(f'{field}{relation}{value}')

        query = ' '.join(query_elements)
        return query

    def extract_media_from_product(self, product: dict):
        media_count = int(product.get('mediacount'))
        media_links = []
        for i in range(1, min(media_count + 1, 11)):
            media_link = product.get(f'media{i}')
            if media_link:
                media_links.append(media_link)

        # All images after index 10 are stored in 'mediax' and delimited by '*'
        if media_count > 10:
            extra_links = product.get('mediax', '').split('*')
            for link in extra_links:
                if link:
                    media_links.append(link)

        return media_links

    def update_product_details(self, updated_product_data: dict, store_type: str, store_instance_id: int,
                               old_product_data=None, skip_all_channels=False):
        """
        Updates the product on SureDone. If the old_product_data param is provided, it verifies that no variations
        got deleted via UI. If some variation got deleted this function will also delete the deleted variations from
        SureDone.

        :param updated_product_data:
        :type updated_product_data:
        :param store_type: can be one of: ['ebay', 'amzn', 'facebook']
        :type store_type: str
        :param store_instance_id:
        :type store_instance_id:
        :param old_product_data:
        :type old_product_data:
        :param skip_all_channels:
        :type skip_all_channels:
        :return:
        :rtype:
        """
        product_data = deepcopy(updated_product_data)

        # Get channels to skip config
        if not skip_all_channels:
            skip_channels_config = self.get_skip_channels_config(store_type, store_instance_id)
            product_data.update(skip_channels_config)

        # Step 1: Get variants
        variants = product_data.pop('variants', [])
        total_new_variants_count = len(variants) if variants else 1

        # Step 2: Verify that no variations got deleted, handle if any got deleted, then split into per-variant data
        data_per_variant = []

        # Case 1: The new number of variants is smaller than before
        if isinstance(old_product_data, list) and len(old_product_data) > total_new_variants_count:
            old_product_data_dict = {data.get('guid'): data for data in old_product_data}
            parent_guid = old_product_data[0].get('sku')
            all_children_guids = [guid for guid in old_product_data_dict.keys() if guid != parent_guid]
            all_children_guids.reverse()

            if len(variants) > 0:
                for i, variant in enumerate(variants):
                    old_guid = variant.get('guid')
                    new_guid = parent_guid if i == 0 else all_children_guids.pop()

                    current_variant_data = deepcopy(old_product_data_dict.get(old_guid))
                    current_variant_data.update({
                        **product_data,
                        **variant,
                        'guid': new_guid
                    })
                    data_per_variant.append(current_variant_data)
            else:
                product_data['guid'] = parent_guid
                data_per_variant = [product_data]

            # Delete the remaining children product variants
            if len(all_children_guids) > 0:
                api_response = self.delete_products_by_guid(all_children_guids)
                if api_response.get('result') != 'success':
                    # TODO: add handling for failed deletion
                    return

        # Case 3: The new number of the variants is the same as before
        else:
            data_per_variant = self.generate_data_per_variant(product_data, variants)

        # Step 3: Transform data into array-based data
        # Exclude 'sku' field in the final request to SureDone because the field is readonly
        api_request_data = self.transform_variant_data_into_sd_list_format(data_per_variant, ['sku'])

        return self.api.edit_product_details_bulk(api_request_data, skip_all_channels)

    def relist_product(self, guids: List[str], store_type: str, store_instance_id: int):
        skip_channels_config = self.get_skip_channels_config(store_type, store_instance_id)
        request_data = [{
            'guid': guid,
            'dropifiedconnectedstoreid': store_instance_id,
            **skip_channels_config,
        } for guid in guids]
        api_request_data = self.transform_variant_data_into_sd_list_format(request_data)
        return self.api.relist_product_details_bulk(api_request_data)

    def generate_data_per_variant(self, root_data: dict, variants_specific_data: list) -> list:
        data_per_variant = []
        if len(variants_specific_data) > 0:
            for variant in variants_specific_data:
                current_variant_data = deepcopy(root_data)
                current_variant_data.update(variant)
                data_per_variant.append(current_variant_data)
        else:
            data_per_variant = [root_data]

        return data_per_variant

    def format_error_messages_by_variant(self, errors: dict) -> str:
        return '\n\n'.join([f'<b>Variant #{i}</b>: {m}' for i, m in errors.items()])

    def transform_variant_data_into_sd_list_format(self, data_per_variant: list, keys_to_exclude=None):
        if not keys_to_exclude:
            keys_to_exclude = []
        # Get all possible keys across all variants
        keys_set = list(set().union(*(d.keys() for d in data_per_variant)))
        # Exclude 'guid' field to move it to the first position in all keys
        extended_keys_to_exclude = keys_to_exclude + ['guid']
        all_keys = ['guid'] + list(filter(lambda x: x not in extended_keys_to_exclude, keys_set))

        # Transform a list of dicts to a list of lists
        # First element is a list of all keys
        api_request_data = [all_keys]
        # Rest of elements are values for each variant in the same order as keys in all_keys
        api_request_data += [
            [
                variant_data[key] if key in variant_data else ''
                for key in all_keys
            ]
            for variant_data in data_per_variant
        ]
        return api_request_data

    def format_image_urls_as_sd_media(self, image_urls: list):
        current_img_indx = 1
        media_data = {'mediax': ''}

        # Map each image element to a corresponding "media" field
        for image in image_urls:
            # CASE 1: First 10 images urls are mapped to fields "mediai" where i is the index from 1 to 10
            if current_img_indx <= 10:
                media_data[f'media{current_img_indx}'] = image

            # CASE 2: All remaining image urls get mapped to mediax delimited by *
            else:
                media_data['mediax'] += f'{image}*'
            current_img_indx += 1

        # Remove the trailing delimiting "*" symbol if there the mediax field is defined
        if current_img_indx > 10 and len(media_data.get('mediax', [])) > 0:
            media_data['mediax'] = media_data['mediax'][:-1]
        return media_data

    def add_variant_images(self, all_variants: list, all_images: list, variants_images: dict):
        # computed_product_data.update(self.format_image_urls_as_sd_media(image_urls))
        hashed_images = [hash_url_filename(image) for image in all_images]

        # Invert the variant images for easier lookup
        inverted_variant_images = {}
        for k, v in variants_images.items():
            try:
                img_index = hashed_images.index(k)
                if v not in inverted_variant_images:
                    inverted_variant_images[v] = [img_index]
                else:
                    inverted_variant_images[v].append(img_index)
            except ValueError:
                continue

        common_images = [i for i, x in enumerate(hashed_images) if x not in variants_images]

        # Add variant-specific image indices to each variant
        for variant in all_variants:
            variant_title = variant.get('varianttitle', '')
            subvariants = [i.strip() for i in variant_title.split('/')]

            temp_images = []
            for subvariant_key in subvariants:
                if subvariant_key in inverted_variant_images:
                    temp_images += inverted_variant_images[subvariant_key]

            variant['temp_images'] = temp_images

            # Add the first (parent) variant's images to common images, so that it's used as a thumbnail
            if variant.get('sku') is not None and variant.get('sku') == variant.get('guid'):
                common_images += temp_images

        # Add images URL's using the computed indices
        for variant in all_variants:
            variant_images = variant.pop('temp_images', []) + common_images
            variant_images = [all_images[i] for i in variant_images]
            variant.update(self.format_image_urls_as_sd_media(variant_images))

    @retry(stop=stop_after_attempt(8), wait=wait_fixed(15))
    def poll_verify_custom_fields_created(self, pending_fields: list):
        all_options_data = self.get_all_user_options(update_db=False)
        if not self.sd_account.has_fields_defined(pending_fields, all_options_data):
            raise Exception
        else:
            self.sd_account.update_options_config(all_options_data, overwrite=True)

    def handle_non_variant_fields(self, non_created_fields: list, non_variation_fields: list):
        all_options_data = self.get_all_user_options()

        # Verify that the fields don't exist and not that the options are not synced
        all_fields_defined = self.sd_account.has_fields_defined(non_created_fields, all_options_data)
        all_variations_set = self.sd_account.has_variation_fields(non_variation_fields, all_options_data)

        # Create missing fields
        pending_fields = []
        if not all_fields_defined and non_created_fields:
            pending_fields = [self.sd_account.format_custom_field(x) for x in non_created_fields]
            failed_sets = self.create_custom_fields([{
                'name': pending_fields,
                'label': non_created_fields,
                'type': 'varchar',
                'length': 200
            }], tries=1)
            if failed_sets:
                try:
                    # Try parsing errors
                    failed_field_names = []
                    if isinstance(failed_sets[0], dict):
                        errors = failed_sets[0].get('errors', {}).get('user_field_names_addname')
                        if errors and isinstance(errors, str):
                            # Remove extra error text
                            errors = errors.replace(' error adding user fields', '').replace('"', '')
                            # Extract failed field names
                            failed_field_names = errors.split(',')
                            # Filter out failed field names from the pending fields
                            pending_fields = [x for x in pending_fields if x not in failed_field_names]
                    if not isinstance(failed_sets[0], dict) or failed_field_names:
                        capture_message('Error creating custom fields for a product', extra={
                            'failed_sets': failed_sets,
                            'failed_field_names': failed_field_names,
                            'non_created_fields': non_created_fields,
                            'sd_account_id': self.sd_account.id
                        })
                except IndexError:
                    capture_message('Error creating custom fields', extra={
                        'failed_sets': failed_sets,
                        'non_created_fields': non_created_fields,
                        'sd_account_id': self.sd_account.id
                    })

        # Add variation fields settings
        if not all_variations_set and non_variation_fields:
            # Poll options to wait for the fields to get created
            if pending_fields:
                try:
                    self.poll_verify_custom_fields_created(pending_fields)
                except RetryError:
                    capture_message('Timed out waiting for pending fields to get created', extra={
                        'pending_fields': pending_fields,
                        'sd_account_id': self.sd_account.id
                    })

            # Try updating variation settings
            formatted_fields = [x if x not in non_created_fields else self.sd_account.format_custom_field(x)
                                for x in non_variation_fields]
            request_data = {'site_cart_variants_set': formatted_fields}
            api_resp = self.api.update_user_settings(request_data)
            try:
                api_resp_data = api_resp.json()
                error_messages = api_resp_data.get('errors', {}).get('site_cart_variants_set')
                if api_resp_data.get('result') != 'success' or error_messages:
                    capture_message('Request to set custom fields variations failed.', extra={
                        'suredone_account_id': self.sd_account.id,
                        'response_code': api_resp.status_code,
                        'response_reason': api_resp.reason,
                        'response_data': api_resp_data,
                        'failed_variant_fields': non_variation_fields,
                    })
            except Exception:
                capture_exception(extra={
                    'description': 'Exception error when trying to set custom field variants.',
                    'suredone_account_id': self.sd_account.id,
                    'response_code': api_resp.status_code,
                    'response_reason': api_resp.reason,
                    'failed_variant_fields': non_variation_fields
                })

    def parse_product_details_in_ext_format(self, product_data: dict):
        computed_product_data = deepcopy(product_data)
        data_per_variant = []

        # Generate parent GUID and SKU
        parent_guid_prefix = uuid.uuid4().hex[:10].upper()
        main_sku = f'{parent_guid_prefix}-1'
        store_instance_id = product_data.get('dropifiedconnectedstoreid', '')

        # Step 1: Remap image urls to SureDone media format
        all_images = computed_product_data.pop('images', [])
        computed_product_data['allimages'] = json.dumps(all_images)

        # Step 2: Rename Dropified-SureDone incompatible fields
        dropified_to_sd_fields_map = {
            'description': 'longdescription',
            'type': 'producttype',
        }
        for dropified_key in dropified_to_sd_fields_map.keys():
            sd_key = dropified_to_sd_fields_map[dropified_key]
            computed_product_data[sd_key] = computed_product_data.pop(dropified_key, '')

        # Add the required "condition" field
        computed_product_data['condition'] = computed_product_data.get('condition', 'New')

        # Add the field brand derived from the vendor field
        computed_product_data['brand'] = computed_product_data.get('vendor', '')

        # Step 3: Stringify store field value
        store_info = computed_product_data.pop('store', None)
        if store_info:
            computed_product_data['store'] = json.dumps(store_info)

        # Step 4: Drop all fields with None values
        computed_product_data = {k: v for k, v in computed_product_data.items() if v is not None}

        if 'weight' not in computed_product_data:
            computed_product_data['weight'] = '0.0'

        # Step 4: Split variants into separate products
        req_variants = computed_product_data.pop('variants', [])
        # Save variant titles to keep formatting
        variant_titles = [v.get('title') for v in req_variants]
        req_variants_info = computed_product_data.pop('variants_info', {})
        req_variants_sku = computed_product_data.pop('variants_sku', {})
        req_variants_images = computed_product_data.pop('variants_images', {})

        for variant in req_variants:
            variant['title'] = variant.get('title', '').lower()

        computed_product_data['variantsconfig'] = json.dumps(req_variants)

        for dropified_key in list(computed_product_data.keys()):
            sd_key = dropified_key.replace('_', '')
            computed_product_data[sd_key] = computed_product_data.pop(dropified_key, '')

        computed_product_data['stock'] = 2

        if len(req_variants) > 0:
            variation_types = [i.get('title') for i in req_variants]

            # Generate parent GUID and SKU
            computed_product_data['sku'] = main_sku

            # If variants_info wasn't provided in the product data, generate it manually
            if not req_variants_info:
                all_var_values = [v['values'] for v in req_variants if len(v.get('values', [])) > 0]
                if len(all_var_values):
                    for variant_comb in itertools.product(*all_var_values):
                        req_variants_info[' / '.join(variant_comb)] = {}

            # Parse each variant combination to create a separate product for it
            for var_info_i, variant_title in enumerate(req_variants_info.keys()):
                current_variant_data = deepcopy(computed_product_data)
                current_variant_data['varianttitle'] = variant_title
                current_variant_data['guid'] = f'{parent_guid_prefix}-{var_info_i+1}'

                # Add values for the variation fields
                var_unique_values = [x.strip() for x in variant_title.split('/')]
                non_created_fields = []
                non_variation_fields = []
                for i, key in enumerate(variation_types):
                    try:
                        current_variant_data[key] = var_unique_values[i]
                        current_variant_data[f'ebay{store_instance_id}itemspecifics{key}'] = var_unique_values[i]
                        current_variant_data[self.sd_account.format_custom_field(key)] = var_unique_values[i]
                        if not self.sd_account.has_field_defined(key):
                            non_created_fields.append(variant_titles[i])
                        if not self.sd_account.has_variation_field(key):
                            non_variation_fields.append(variant_titles[i])
                    except IndexError:
                        continue

                if non_created_fields or non_variation_fields:
                    self.handle_non_variant_fields(non_created_fields, non_variation_fields)

                # For each field within the current variant (price, compare_at, sku, image)
                for key in req_variants_info[variant_title]:
                    if key == 'compare_at':
                        current_variant_data['compareatprice'] = req_variants_info[variant_title][key]
                    if key == 'sku':
                        current_variant_data['suppliersku'] = req_variants_info[variant_title][key]
                    else:
                        current_variant_data[key.replace('_', '')] = req_variants_info[variant_title][key]

                # Parse variant's supplier sku
                supplier_sku = ''
                for var_value in var_unique_values:
                    supplier_sku += req_variants_sku.get(var_value, '') + ';'
                if supplier_sku:
                    # Remove the trailing ';'
                    supplier_sku = supplier_sku[:-1]
                    current_variant_data['suppliersku'] = supplier_sku

                data_per_variant.append(current_variant_data)
        else:
            computed_product_data['guid'] = main_sku
            computed_product_data['sku'] = main_sku
            data_per_variant.append(computed_product_data)

        if not req_variants_images:
            sd_media = self.format_image_urls_as_sd_media(all_images)
            for i, x in enumerate(data_per_variant):
                data_per_variant[i].update(sd_media)
        else:
            self.add_variant_images(data_per_variant, all_images, req_variants_images)

        return {'data_per_variant': data_per_variant, 'parent_guid': main_sku}

    def add_product_draft(self, ext_formatted_product_data: dict, store_instance_id: int, store_type: str):
        """
        Add a new product draft without listing it on eBay.
        Expects the Dropified extension's API request format.

        :param ext_formatted_product_data:
        :type ext_formatted_product_data: dict
        :param store_instance_id:
        :type store_instance_id:
        :param store_type: can be one of: ['ebay', 'fb']
        :type store_type: str
        :return: SureDone's API response
        :rtype: JsonResponse
        """
        # Add Dropified data about connected store
        ext_formatted_product_data.update({
            'dropifiedconnectedstoretype': store_type,
            'dropifiedconnectedstoreid': store_instance_id,
        })

        # Parse the extension-formatted data and transform it to match SureDone field names format
        sd_formatted_data = self.parse_product_details_in_ext_format(ext_formatted_product_data)

        # Transform the SureDone data from a dictionary format into an array-based bulk edit format
        api_request_data = self.transform_variant_data_into_sd_list_format(sd_formatted_data.get('data_per_variant', {}))
        api_response = self.api.add_products_bulk(api_request_data, skip_all_channels=True)

        return {
            'parent_guid': sd_formatted_data.get('parent_guid', ''),
            'api_response': api_response
        }

    def add_product(self, product_data: dict, store_instance_id: int, store_type: str):
        """
        Add a new product without listing it on eBay.

        :param product_data:
        :type product_data: dict
        :param store_instance_id:
        :type store_instance_id:
        :param store_type:
        :type store_type:
        :return: SureDone's API response
        :rtype: JsonResponse
        """
        # Add Dropified data about connected store
        product_data.update({
            'dropifiedconnectedstoretype': store_type,
            'dropifiedconnectedstoreid': store_instance_id,
        })

        # Transform the SureDone data from a dictionary format into an array-based bulk edit format
        api_request_data = self.transform_variant_data_into_sd_list_format([product_data])
        api_response = self.api.add_products_bulk(api_request_data, skip_all_channels=True)

        return {
            'parent_guid': product_data.get('guid', ''),
            'api_response': api_response
        }

    def sd_duplicate_product(self, product_data: list):
        """
        Add a new (duplicated) product without listing it on eBay.

        :param product_data:
        :type: list of dict
        :return: SureDone's API response
        :rtype: JsonResponse
        """

        # Generate new parent GUID and SKU
        parent_guid_prefix = uuid.uuid4().hex[:10].upper()
        main_sku = f'{parent_guid_prefix}-1'

        guid_index = 1
        for product in product_data:
            product['guid'] = f'{parent_guid_prefix}-{guid_index}'
            guid_index += 1
            product['sku'] = main_sku

        # Exclude field in the final request to SureDone
        excluded_fields = ['id', 'mediacount', 'time', 'action', 'uri']
        fields_set = list(set().union(*(d.keys() for d in product_data)))
        for field in fields_set:
            if field[-7:] == 'options':
                excluded_fields.append(field)

        # Transform the SureDone data from a dictionary format into an array-based bulk edit format
        api_request_data = self.transform_variant_data_into_sd_list_format(product_data, excluded_fields)
        api_response = self.api.add_products_bulk(api_request_data, skip_all_channels=True)

        return {
            'api_response': api_response,
            'parent_guid': main_sku,
        }

    def delete_product_with_all_variations(self, parent_guid: str):
        # Get all products with the matching SKU
        sd_product_data = self.api.get_item_by_guid(parent_guid)

        if not (sd_product_data and sd_product_data.get('guid')):
            return

        # Extract GUID values from the children variants
        attributes = list(sd_product_data.get('attributes', {}).values())
        guids_to_delete = [p.get('guid') for p in attributes if p.get('guid')]

        # SureDone doesn't allow to delete a parent until all its children variations are deleted
        # Therefore, add the parent GUID as the last element
        guids_to_delete.append(parent_guid)

        api_response = self.delete_products_by_guid(guids_to_delete)

        return api_response

    def delete_products_by_guid(self, guids_to_delete: list):
        # Reformat for SureDone API
        reformatted_guids = [[i] for i in guids_to_delete]
        api_request_data = [['guid'], *reformatted_guids]

        # Delete the products using SureDone API
        api_response = self.api.delete_products_bulk(api_request_data)

        return api_response

    def get_products_by_sku(self, sku_to_find: str, paginate=True, sort=None) -> list:
        sku_filter = self.format_filters({
            'sku': {
                'value': sku_to_find,
                'relation': ':='
            }
        })
        return self.get_all_products(sku_filter, paginate=paginate, sort=sort)

    def get_fields_update_in_all_variants_api_data(self, parent_guid: str, fields_to_update_map: dict):
        # Get all variation products to apply the notes to all variants
        all_products = self.get_products_by_sku(parent_guid, paginate=False)

        if isinstance(all_products, list):
            all_guids = [x.get('guid') for x in all_products if x.get('guid')]
            data_per_variant = [{
                **fields_to_update_map,
                'guid': var_guid,
            } for var_guid in all_guids]
        else:
            data_per_variant = [{
                **fields_to_update_map,
                'guid': parent_guid,
            }]
        return self.transform_variant_data_into_sd_list_format(data_per_variant)

    def get_latest_order_note(self, order_id):
        r = self.api.get_order_details(order_id)
        orders_data = r.get('orders', [])

        if isinstance(orders_data, list) and len(orders_data) > 0:
            try:
                all_notes = list(orders_data[0].get('internalnotes', {}).items())
                latest_note = all_notes[-1]
                if latest_note:
                    return latest_note[1]
            except:
                pass

        return ''

    def format_error_messages(self, count_field_name: str, api_response: dict) -> str:
        total_variants_count = safe_int(api_response.get(count_field_name))
        resp_per_var = {i: api_response.get(f'{i}', {}) for i in range(1, total_variants_count + 1)}

        all_err_messages = {k: v.get('errors') for k, v in resp_per_var.items() if v.get('result') != 'success'}
        if len(all_err_messages) > 0:
            formatted_error_msg = '\n\n'.join([f'<b>Variant #{i}</b>: {m}' for i, m in all_err_messages.items()])
            return formatted_error_msg
        return ''

    def update_user_business_settings(self, config: dict):
        api_resp = self.api.update_settings(config)
        error = False
        error_message = ''
        if not isinstance(api_resp, dict) or api_resp.get('result') != 'success':
            error = True
            if isinstance(api_resp, dict):
                error_message = api_resp.get('message', '')
        if not error:
            self.sd_account.update_options_config(config)
        return {'error': error, 'error_message': error_message}

    def create_custom_fields(self, custom_fields_sets: list, tries=3):
        """
        Run new SureDone user account setup steps
        :param custom_fields_sets: Groups of custom fields configuration
        :type custom_fields_sets: list
        :param tries: Number of times to reattempt in case of an error
        :type tries: int
        :return: A dictionary containing keys of failed fields groups and api responses for each as its value
        :rtype: dict
        """
        if not self.api:
            return {i: {} for i in enumerate(custom_fields_sets)}

        failed_set_indices = {}
        for i, fields_set in enumerate(custom_fields_sets):
            tries_left = tries
            success = False
            request_data = {f'user_field_names_add{k}': v for k, v in fields_set.items()}
            request_data['user_field_names_addbulk'] = True

            api_resp = {}
            while tries_left > 0:
                api_resp = self.api.update_settings(request_data)
                if isinstance(api_resp, dict) and api_resp.get('result') == 'success' and not api_resp.get('errors'):
                    success = True
                    break
                tries_left -= 1

            if not success:
                failed_set_indices[i] = api_resp

        return failed_set_indices

    def update_product_variant(self, updated_product_data: dict, skip_all_channels=True):
        """
        Updates the variant of product on SureDone.

        :param updated_product_data: product data for update
        :type updated_product_data: dict
        :param skip_all_channels:
        :type skip_all_channels: bool
        :return: SureDone's API response
        :rtype: JsonResponse
        """
        # Transform data into array-based data
        api_request_data = self.transform_variant_data_into_sd_list_format([updated_product_data])

        return self.api.edit_product_details_bulk(api_request_data, skip_all_channels)

    def store_shipping_carriers(self):
        carriers = [
            {1: 'USPS'}, {2: 'UPS'}, {3: 'FedEx'}, {4: 'LaserShip'},
            {5: 'DHL US'}, {6: 'DHL Global'}, {7: 'Canada Post'},
            {8: 'Custom Provider'},
        ]

        return [{'id': list(c.keys()).pop(), 'title': list(c.values()).pop()} for c in carriers]

    def get_shipping_carrier_name(self, carrier_id):
        shipping_carriers = self.store_shipping_carriers()
        for carrier in shipping_carriers:
            if carrier['id'] == carrier_id:
                return carrier['title']

    def get_orders_by_platform_type(self, store, filters: dict, page=None, per_page=None):
        if not page:
            page = 1
        if not per_page:
            per_page = 25

        # SD assigns instance IDs in the following order: 0, 2, 3, 4, etc., so if the instance ID is 1, set it to 0
        try:
            instance_id_filter = store.filter_instance_id
        except InvalidSureDoneStoreInstanceId:
            capture_exception()
            instance_id_filter = store.store_instance_id

        search_filters = {
            'channel': {
                'value': filters.get('platform_type'),
                'relation': ':='
            },
            'instance': {
                'value': instance_id_filter,
                'relation': ':='
            },
            'archived': {
                'value': '0',
                'relation': ':='
            }
        }

        sort_by = None
        sort_order = None

        # Parse and format filters
        if filters:
            order_by = filters.get('orderby')
            if order_by:
                sort_by = order_by

            order = filters.get('order')
            if order:
                sort_order = order

            customer_filter = filters.get('customer')
            if customer_filter:
                first_name = customer_filter.get('first_name')
                if first_name:
                    search_filters['sfirstname'] = {
                        'value': first_name,
                        'relation': ':'
                    }

                last_name = customer_filter.get('last_name')
                if last_name:
                    search_filters['slastname'] = {
                        'value': last_name,
                        'relation': ':'
                    }

                email = customer_filter.get('email')
                if email:
                    search_filters['email'] = {
                        'value': email,
                        'relation': ':='
                    }

            order_id = filters.get('order_id')
            if order_id:
                search_filters['ordernumber'] = {
                    'value': order_id,
                    'relation': ':'
                }

            country = filters.get('country')
            if country:
                search_filters['scountry'] = {
                    'value': country,
                    'relation': ':='
                }

            status = filters.get('status')
            if status:
                search_filters['status'] = {
                    'value': status,
                    'relation': ':='
                }

            oid = filters.get('oid')
            if oid:
                search_filters['oid'] = {
                    'value': oid,
                    'relation': ':='
                }

        search_filters = self.format_filters(search_filters)

        # Format time filters
        if filters and ('after' in filters or 'before' in filters):
            time_filters = []
            before_filter = filters.get('before', '')
            after_filter = filters.get('after', '')

            if before_filter:
                time_filters.append(self.format_filters({'date': {'value': before_filter, 'relation': ':<='}}))
            if after_filter:
                time_filters.append(self.format_filters({'date': {'value': after_filter, 'relation': ':>='}}))

            search_filters = f"{search_filters} {' '.join(time_filters)}"

        return self.get_all_orders(search_filters,
                                   page=page,
                                   sort_by=sort_by,
                                   sort_order=sort_order)

    def get_item_fulfillment_status(self, order: dict, item_id):
        shipments = order.get('shipments', [])
        status = 'Unfulfilled'
        for shipment_info in shipments:
            try:
                shipment_items = shipment_info.get('shipdetails', {}).get('items')
            except AttributeError:
                continue
            if not isinstance(shipment_items, list):
                continue

            skus = [x.get('sku') for x in shipment_items if 'sku' in x]
            for sku in skus:
                if sku == item_id:
                    status = 'Fulfilled'
                    return status

        return status

    def order_id_from_name(self, store, order_name, default=None):
        order_name = order_name.replace('#', '')
        if not order_name:
            return default

        sd_orders, sd_orders_count = self.get_all_orders(filters=f'{order_name}')

        if sd_orders_count and len(sd_orders):
            return [i.get('oid') for i in sd_orders]

        return default

    def convert_to_default_and_custom_fields(self, fields: List[str]) -> List[str]:
        return [field if self.sd_account.is_default_field(field) else self.sd_account.format_custom_field(field)
                for field in fields]


class SureDoneAdminUtils:
    def generate_sd_username(self, user, test=False):
        username = f'user-id{user.models_user.id}-{get_random_string(4)}'
        if test:
            username_suffix = f'TEST-{arrow.utcnow().timestamp}'
        else:
            username_suffix = 'PROD'
        return f'{username}_{username_suffix}'

    def generate_sd_email(self, username: str):
        return f'suredone+{username}@dropified.com'

    def register_new_user(self, user):
        username = self.generate_sd_username(user, test=settings.DEBUG)
        email = self.generate_sd_email(username)
        password = get_random_string(12)
        error = ''
        api_resp = SureDoneAdminApiHandler.register_user(username=username, email=email, password=password)

        try:
            api_resp.raise_for_status()
            user_data = api_resp.json()
            if user_data.get('result') != 'success':
                capture_message('Request to create a new SureDone user failed.', extra={
                    'username': username,
                    'email': email,
                    'password': password,
                    'response_code': api_resp.status_code,
                    'sd_response': user_data
                })
                return {'error': user_data['message'], 'account': None}
        except Exception:
            capture_exception(extra={
                'description': 'Error when trying to parse SureDone new account creation response',
                'username': username,
                'email': email,
                'password': password,
                'response_code': api_resp.status_code,
                'response_reason': api_resp.reason,
            })
            return {'error': 'Something went wrong, please try again.', 'account': None}

        new_account = SureDoneAccount(
            user=user.models_user,
            title=f'{"Test-" if settings.DEBUG else ""}user {user.models_user.id} auto-created SureDone account',
            email=email,
            password=password,
            sd_id=user_data.get('userid'),
            api_username=user_data.get('username'),
            api_token=user_data.get('token'),
            is_active=True,
        )

        new_account.save()
        return {'error': error, 'account': new_account}

    def list_all_users(self):
        api_resp = SureDoneAdminApiHandler.list_all_users()
        error = ''
        users = []
        if api_resp.get('result') != 'success':
            error = api_resp.get('message')
            error = error or 'Failed to fetch SureDone users'

        try:
            users = list(api_resp.get('users', {}).values())
        except Exception as e:
            error = e
        return {'users': users, 'error': error}


class SureDonePusher:
    def __init__(self, channel):
        self.channel = channel
        self.pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

    def trigger(self, event, data, channel=None):
        channel = self.channel if channel is None else channel
        self.pusher.trigger(channel, event, data)


class SureDoneOrderUpdater:
    store_model = None
    utils_class = None

    def __init__(self, user=None, store=None, order_id: int = None):
        self.utils = None
        self.user = user
        if user and self.utils_class is not None:
            self.utils = self.utils_class(user)
        self.store = store
        self.order_id = order_id
        self.notes = []

    def add_note(self, n):
        self.notes.append(n)

    def mark_as_ordered_note(self, line_id: str, source_id: int, track):
        source = 'Aliexpress'

        if track:
            url = track.get_source_url()
            source = track.get_source_name()

        else:
            url = f'https://trade.aliexpress.com/order_detail.htm?orderId={source_id}'

        note = f'{source} Order ID: {source_id}\n{url}'

        if line_id:
            note = f'{note}\nOrder Line: #{line_id}'

        self.add_note(note)

    def save_changes(self):
        with cache.lock(f'updater_lock_{self.store.id}_{self.order_id}', timeout=15):
            self._do_save_changes()

    def _do_save_changes(self):
        if self.notes:
            new_note = '\n'.join(self.notes)
            self.add_order_note(self.order_id, new_note)

    def toJSON(self, additional_values: dict = None):
        if additional_values is None:
            additional_values = {}

        return json.dumps({
            "notes": self.notes,
            "order": self.order_id,
            "user": self.user.models_user.id,
            "store": self.store.id,
            **additional_values
        }, sort_keys=True, indent=4)

    def fromJSON(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        self.store = self.store_model.objects.get(id=data.get('store'))
        self.order_id = data.get('order')
        self.user = User.objects.get(id=data.get('user'))
        if self.user and self.utils_class is not None:
            self.utils = self.utils_class(self.user)
        self.notes = data.get('notes')

    def add_order_note(self, order_id: int, note: str):
        if not self.utils:
            raise AttributeError('Error saving an order note: No user was provided.')

        request_body = {
            'internalnotes': note,
            'oid': order_id,
        }

        r = self.utils.api.update_order_details(order_id, request_body)
        r.raise_for_status()

        return r.json()

    def update_order_status(self, status, tries=3):
        while tries > 0:
            tries -= 1
            r = self.utils.api.update_order_details(self.order_id, {'status': status})
            if r.ok:
                break


def get_or_create_suredone_account(user) -> SureDoneAccount:
    # Check if the user already has a suredone account
    try:
        sd_account = SureDoneAccount.objects.get(user=user.models_user, is_active=True)
    except SureDoneAccount.DoesNotExist:
        # Try finding a SureDone user using SD API by user ID
        result = SureDoneAdminUtils().register_new_user(user)
        sd_account = result.get('account')
        if result.get('error') or sd_account is None:
            capture_message('Error creating a new account.', extra={'error_message': result.get('error')})
    except SureDoneAccount.MultipleObjectsReturned:
        sd_account = SureDoneAccount.objects.filter(user=user.models_user, is_active=True).first()

    return sd_account


def add_suredone_account(user, data: dict):
    """
    Add a new SureDone account to the current user

    :param user:
    :param data:
        title (str)
        api_username (str)
        api_token (str)
    :type data: dict
    :return:
    :rtype:
    """
    title = data.get('title', '').strip()
    suredone_username = data.get('api_username', '').strip()
    suredone_token = data.get('api_token', '').strip()

    error_messages = []

    if len(title) > SureDoneAccount._meta.get_field('title').max_length:
        error_messages.append('Title is too long.')

    try:
        # TODO: validate credentials
        pass
    except:
        error_messages.append('API Credentials are incorrect.')

    if len(error_messages) > 0:
        return error_messages

    store = SureDoneAccount(
        user=user.models_user,
        title=data.get('title', '').strip(),
        api_username=suredone_username,
        api_token=suredone_token
    )

    store.save()

    return error_messages


def get_daterange_filters(created_at_daterange):
    after, before = created_at_daterange.split('-')
    month, day, year = after.split('/')
    after_date = arrow.get(int(year), int(month), int(day))
    month, day, year = before.split('/')
    before_date = arrow.get(int(year), int(month), int(day))

    return after_date.isoformat(), before_date.ceil('day').isoformat()


def sd_customer_address(shipping_address: dict, phone: str, aliexpress_fix=False, german_umlauts=False,
                        aliexpress_fix_city=False, return_corrections=False,
                        shipstation_fix=False):
    customer_address = {}

    for k in shipping_address.keys():
        if shipping_address[k] and type(shipping_address[k]) is str:
            v = re.sub(' ?\xc2?[\xb0\xba] ?', r' ', shipping_address[k])
            if german_umlauts:
                v = re.sub('\u00e4', 'ae', v)
                v = re.sub('\u00c4', 'AE', v)
                v = re.sub('\u00d6', 'OE', v)
                v = re.sub('\u00fc', 'ue', v)
                v = re.sub('\u00dc', 'UE', v)
                v = re.sub('\u00f6', 'oe', v)

            customer_address[k] = unidecode(v)
        else:
            customer_address[k] = shipping_address[k]

    first_name = customer_address.get('first_name', '').strip()
    last_name = customer_address.get('last_name', '').strip()

    customer_address['name'] = f'{first_name} {last_name}'
    customer_address['address1'] = customer_address.get('address_1')
    if customer_address.get('number'):
        customer_address['address1'] += f", {customer_address.get('number')}"
    customer_address['address2'] = customer_address.get('address_2')
    customer_address['country_code'] = customer_address.get('country')
    customer_address['province_code'] = customer_address.get('state')
    customer_address['zip'] = customer_address.get('postcode')
    customer_address['country'] = country_from_code(customer_address['country_code'], '')

    if shipstation_fix:
        customer_address['province'] = customer_address.get('state')
        customer_address['phone'] = phone
        return supplement_customer_address(customer_address)

    province = province_from_code(customer_address['country_code'], customer_address['province_code'])
    customer_address['province'] = unidecode(province) if type(province) is str else province

    customer_province = customer_address['province']

    if not customer_address.get('province'):
        if customer_address['country'].lower() == 'united kingdom' and customer_address['city']:
            province = get_uk_province(customer_address['city'])
            customer_address['province'] = province
        else:
            customer_address['province'] = customer_address['country_code']

    elif customer_address['province'] == 'Washington DC':
        customer_address['province'] = 'Washington'

    elif customer_address['province'] == 'Puerto Rico':
        # Puerto Rico is a country in Aliexpress
        customer_address['province'] = 'PR'
        customer_address['country_code'] = 'PR'
        customer_address['country'] = 'Puerto Rico'

    elif customer_address['province'] == 'Virgin Islands':
        # Virgin Islands is a country in Aliexpress
        customer_address['province'] = 'VI'
        customer_address['country_code'] = 'VI'
        customer_address['country'] = 'Virgin Islands (U.S.)'

    elif customer_address['province'] == 'Guam':
        # Guam is a country in Aliexpress
        customer_address['province'] = 'GU'
        customer_address['country_code'] = 'GU'
        customer_address['country'] = 'Guam'

    if customer_address['country_code'] == 'FR':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t\._ -]', '', customer_address['zip']).strip().rjust(5, '0')

    if customer_address['country_code'] == 'BR':
        customer_address = fix_br_address(customer_address)

    if customer_address['country_code'] == 'IL':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t\._ -]', '', customer_address['zip']).strip().rjust(7, '0')

    if customer_address['country_code'] == 'CA':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t ]', '', customer_address['zip']).upper().strip()

        if customer_address['province'] == 'Newfoundland':
            customer_address['province'] = 'Newfoundland and Labrador'

    if customer_address['country'].lower() == 'united kingdom':
        if customer_address.get('zip'):
            if not re.findall(r'^([0-9A-Za-z]{2,4}\s[0-9A-Za-z]{3})$', customer_address['zip']):
                customer_address['zip'] = re.sub(r'(.+)([0-9A-Za-z]{3})$', r'\1 \2', customer_address['zip'])

    if customer_address['country_code'] == 'MK':
        customer_address['country'] = 'Macedonia'

    if customer_address['country_code'] == 'PL':
        if customer_address.get('zip'):
            customer_address['zip'] = re.sub(r'[\n\r\t\._ -]', '', customer_address['zip'])

    if customer_address.get('company'):
        customer_address['name'] = f"{first_name} {last_name} - {customer_address['company']}"

    correction = {}
    if aliexpress_fix:
        valid, correction = valide_aliexpress_province(
            customer_address['country'],
            customer_address['province'],
            customer_address['city'],
            auto_correct=True)

        if not valid:
            if support_other_in_province(customer_address['country']):
                customer_address['province'] = 'Other'

                if customer_address['country'].lower() == 'united kingdom' and customer_address['city']:
                    province = get_uk_province(customer_address['city'])
                    if province:
                        customer_address['province'] = province

                if customer_province and customer_address['province'] == 'Other':
                    customer_address['city'] = f"{customer_address['city']}, {customer_province}"

            elif aliexpress_fix_city:
                city = safe_str(customer_address['city']).strip().strip(',')
                customer_address['city'] = 'Other'

                if not safe_str(customer_address['address2']).strip():
                    customer_address['address2'] = f'{city},'
                else:
                    customer_address['address2'] = f"{customer_address['address2'].strip().strip(',')}, {city},"

        elif correction:
            if 'province' in correction:
                customer_address['province'] = correction['province']

            if 'city' in correction:
                customer_address['city'] = correction['city']

    if return_corrections:
        return customer_address, correction
    else:
        return customer_address
