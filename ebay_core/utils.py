import arrow
import csv
import itertools
import json
import re
import requests

from django.contrib.auth.models import User
from django.core.cache import cache, caches
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone

import leadgalaxy.utils as leadgalaxy_utils
from ebay_core.models import EbayBoard, EbayOrderTrack, EbayProduct, EbayProductVariant, EbayStore, EbaySupplier
from leadgalaxy.models import UserProfile
from lib.exceptions import capture_exception
from shopified_core import permissions
from shopified_core.decorators import add_to_class
from shopified_core.paginators import SimplePaginator
from shopified_core.utils import (
    fix_order_data,
    http_exception_response,
    http_excption_status_code,
    products_filter,
    safe_float,
    safe_int,
    safe_json,
    safe_str
)
from suredone_core.models import InvalidSureDoneStoreInstanceId, SureDoneAccount
from suredone_core.utils import SureDoneUtils, get_or_create_suredone_account, parse_suredone_date, sd_customer_address


class EbayUtils(SureDoneUtils):
    def authorize_new_channel_using_oauth(self, ebay_username: str):
        """
        Performs the steps required to authoriza ebay via OAuth
        Note: OAuth goes after the Auth'n'Auth step, so assumes all user's Dropified permissions are valid
        :param ebay_username: ebay username returned by ebay's Auth'n'Auth redirection URL
        :type ebay_username: str
        :return: A dictionary with items:
            'auth_url': the authorization url
            'error': error message if there was an error otherwise an empty string
        :rtype: dict
        """
        sd_account = get_or_create_suredone_account(self.user)

        if not sd_account:
            return {'error': 'Failed to set up an eBay store. Please try again'}

        self._reload_api(account_id=sd_account.id)

        # Step 1: Get all user options config
        options_conf = self.get_all_user_options()

        # Step 2: Find an ebay instance with the matching username
        channel_inst_to_use = None
        ebay_plugin_settings = safe_json(options_conf.get('plugin_settings', '{}')).get('channel', {}).get('ebay', {})

        default_ebay_channel_username = safe_json(options_conf.get('ebay_user_data')).get('UserID')
        # If the first ebay instance username is matching
        if default_ebay_channel_username and default_ebay_channel_username == ebay_username:
            channel_inst_to_use = 1
        else:
            # Look in other ebay user data configs
            ebay_channel_ids = [x.get('instanceId', 0) for x in ebay_plugin_settings.values()]
            for channel_id in ebay_channel_ids:
                current_inst_user_data = safe_json(options_conf.get(f'{self.get_ebay_prefix(channel_id)}_user_data'))
                if isinstance(current_inst_user_data, dict) and current_inst_user_data.get('UserID') == ebay_username:
                    channel_inst_to_use = channel_id

        # If default and all additional ebay usernames are not matching then need to redo the Auth'n'Auth step
        if not channel_inst_to_use:
            return {'error': 'eBay account not found. Please try again.'}
        else:
            channel_prefix = self.get_ebay_prefix(channel_inst_to_use)
            channel_inst_connected = options_conf.get(f'site_{channel_prefix}connect', 'off') == 'on'

        # Enable the channel instance if not enabled yet
        if not channel_inst_connected:
            sd_connect_channel_resp = self.api.update_settings({f'site_{channel_prefix}connect': 'on'})
            if sd_connect_channel_resp.get('result') != 'success':
                return {'error': 'Failed to activate the store. Please try again.'}

        sd_auth_channel_resp = self.api.authorize_channel_v3({'instance': channel_inst_to_use})

        if not isinstance(sd_auth_channel_resp, dict) or 'results' not in sd_auth_channel_resp:
            return {'error': 'Something went wrong, please try again.'}

        sd_resp_results = sd_auth_channel_resp.get('results', {})
        sd_auth_url = sd_resp_results.get('successful', {}).get('auth_url')

        if not sd_auth_url:
            sd_failed_results = sd_resp_results.get('failed')
            error_messages = []

            if isinstance(sd_failed_results, dict):
                error_messages = [x.get('message') for x in sd_failed_results.values() if x.get('message')]

            error = '\n'.join(error_messages) if error_messages else 'Something went wrong. Please try again'
            return {'error': error}

        return {'auth_url': sd_auth_url}

    def sync_ebay_stores(self):
        if not self.api:
            return

        # 1. Get all suredone options
        all_options_data = self.get_all_user_options(verify_custom_fields=True)
        if not isinstance(all_options_data, dict):
            return

        # 2. Extract a list of all ebay channels
        plugin_settings = safe_json(all_options_data.pop('plugin_settings', '{}'))
        additional_ebay_channels = list(plugin_settings.get('channel', {}).get('ebay', {}).values())

        # 3. Sync all store instances
        # 3.1. Check the first and default ebay instance
        self.sync_or_create_store_instance(1, all_options_data)

        # 3.2. Check the rest of the ebay instances
        for channel in additional_ebay_channels:
            instance_id = channel.get('instanceId')
            if instance_id is not None and instance_id != '':
                self.sync_or_create_store_instance(instance_id, all_options_data)

    def get_ebay_user_settings_config(self) -> dict:
        if not self.api:
            return {}

        # 1. Get all suredone options
        all_options_data = self.get_all_user_options()
        if not isinstance(all_options_data, dict):
            return {}

        config = {
            'business_phone': all_options_data.get('business_phone', ''),
            'business_country': all_options_data.get('business_country', ''),
            'business_zip': all_options_data.get('business_zip', ''),
            'site_currency': all_options_data.get('site_currency', '')
        }
        return config

    def get_ebay_advanced_settings(self, store):
        if not self.api:
            return {}

        # 1. Get all suredone options
        all_options_data = self.get_all_user_options()
        if not isinstance(all_options_data, dict):
            return {
                'success': False,
                'message': 'Failed to load user eBay options.'
            }

        ebay_prefix = self.get_ebay_prefix(store.store_instance_id)
        ebay_config = safe_json(all_options_data.get(f'{ebay_prefix}_attribute_mapping'))
        ebay_site_id = all_options_data.get(f'{ebay_prefix}_siteid')

        if not ebay_config:
            return {
                'success': False,
                'message': 'No eBay policy configuration found. Please try again.'
            }

        profile_options = ebay_config.get('profile', {})
        return {
            'success': True,
            'options': {
                'payment_profile_options': list(profile_options.get('payment', {}).values()),
                'return_profile_options': list(profile_options.get('return', {}).values()),
                'shippping_profile_options': list(profile_options.get('shipping', {}).values()),
                'site_id_options': get_ebay_site_id_options(),
            },
            'settings': {
                'payment_profile_id': ebay_config.get('paymentprofileid', ''),
                'return_profile_id': ebay_config.get('returnprofileid', ''),
                'shipping_profile_id': ebay_config.get('shippingprofileid', ''),
                'ebay_siteid': ebay_site_id,
            },
        }

    def sync_or_create_store_instance(self, instance_id: int, all_options_data: dict, instance_title=None):
        if not instance_title:
            ebay_prefix = self.get_ebay_prefix(instance_id)
            ebay_username = safe_json(all_options_data.get(f'{ebay_prefix}_user_data')).get('UserID')
            instance_title = f'eBay:{ebay_username}' if ebay_username else f'eBay-{instance_id}'

        try:
            store = EbayStore.objects.get(store_instance_id=instance_id, user=self.user.models_user)
            store.sync(instance_title, all_options_data)
        except EbayStore.DoesNotExist:
            # Create a new store to reflect the SureDone's data
            prefix = 'ebay' if instance_id == 1 else f'ebay{instance_id}'
            store_enabled = all_options_data.get(f'site_{prefix}connect') == 'on'
            legacy_auth_token = all_options_data.get(f'{prefix}_token')
            oauth_token = all_options_data.get(f'{prefix}_token_oauth')

            is_active = bool(store_enabled and (legacy_auth_token or oauth_token))

            legacy_token_expires_str = all_options_data.get(f'{prefix}_token_expires')
            oauth_token_expires_str = all_options_data.get(f'{prefix}_token_oauth_expires')
            legacy_token_exp_date = None
            oauth_token_exp_date = None

            if legacy_auth_token and legacy_token_expires_str:
                try:
                    arrow_date = arrow.get(legacy_token_expires_str, 'YYYY-MM-DD HH:mm:ss')
                    legacy_token_exp_date = getattr(arrow_date, 'datetime', None)
                except:
                    pass

            if oauth_token and oauth_token_expires_str:
                try:
                    arrow_date = arrow.get(oauth_token_expires_str)
                    oauth_token_exp_date = getattr(arrow_date, 'datetime', None)
                except:
                    pass

            EbayStore.objects.create(
                sd_account=self.sd_account,
                store_instance_id=instance_id,
                user=self.user.models_user,
                title=instance_title,
                is_active=is_active,
                legacy_auth_token_exp_date=legacy_token_exp_date,
                oauth_token_exp_date=oauth_token_exp_date,
            )

    def product_save_draft(self, product_data: dict, store: EbayStore, notes: str, activate: bool):
        """
        Save a new poduct to SureDone without publishing it to any eBay store.
        Parses the API request made by the extension.

        :param product_data: data API param passed by the Dropified extension.
        :type product_data: dict
        :param store:
        :type store:
        :param notes:
        :type notes:
        :param activate:
        :type activate:
        :return:
        :rtype:
        """
        if not self.api:
            return

        sd_api_result = self.add_product_draft(product_data,
                                               store_instance_id=store.store_instance_id,
                                               store_type='ebay')

        # If the product was not successfully posted
        if not isinstance(sd_api_result, dict) or sd_api_result.get('api_response', {}).get('result') != 'success':
            return

        parent_guid = sd_api_result.get('parent_guid')

        # Fetch the product from SureDone and save the product if the product was successfully imported
        created_product = self.get_ebay_product_details(parent_guid, add_model_fields={'notes': notes})

        # If the SureDone returns no data, then the product did not get imported
        if not created_product or not isinstance(created_product, EbayProduct):
            return

        # Init the default supplier
        store_info = product_data.get('store', {})
        original_url = product_data.get('original_url', '')
        supplier = EbaySupplier.objects.create(
            store=store,
            product=created_product,
            product_guid=parent_guid,
            product_url=safe_str(original_url)[:512],
            supplier_name=store_info.get('name') if store_info else '',
            supplier_url=store_info.get('url') if store_info else '',
            is_default=True
        )
        created_product.set_default_supplier(supplier, commit=True)

        return sd_api_result

    def new_product_save(self, product_data: dict, store: EbayStore, notes: str):
        """
        Save a new product to SureDone

        :param product_data: data API param
        :type product_data: dict
        :param store:
        :type store:
        :param notes:
        :type notes:
        :return:
        :rtype:
        """
        if not self.api:
            return

        sd_api_result = self.add_product(
            product_data,
            store_instance_id=store.store_instance_id,
            store_type='ebay'
        )

        # If the product was not successfully posted
        if not isinstance(sd_api_result, dict) or sd_api_result.get('api_response', {}).get('result') != 'success':
            return

        parent_guid = sd_api_result.get('parent_guid')

        # Fetch the product from SureDone and save the product if the product was successfully imported
        created_product = self.get_ebay_product_details(parent_guid, add_model_fields={'notes': notes})

        # If the SureDone returns no data, then the product did not get imported
        if not created_product or not isinstance(created_product, EbayProduct):
            return

        # Init the default supplier
        original_url = product_data.get('originalurl', '')
        supplier = EbaySupplier.objects.create(
            store=store,
            product=created_product,
            product_guid=parent_guid,
            product_url=safe_str(original_url)[:512],
            is_default=True
        )
        created_product.set_default_supplier(supplier, commit=True)

        return sd_api_result

    def sync_ebay_products(self, store_id: str, in_store: str):
        """
        Sync all eBay products.

        :param store_id: eBay store id
        :type store_id: int
        :param in_store:
        :type in_store:
        :return:
        :rtype:
        """
        search_filter = self.format_filters({
            'guid': {
                'value': 'sku',
                'relation': ':='
            },
            'dropifiedconnectedstoretype': {
                'value': 'ebay',
                'relation': ':='
            }
        })

        user_ebay_stores = self.user.profile.get_ebay_stores(do_sync=False)
        ebay_instance_ids = user_ebay_stores.values_list('store_instance_id', flat=True)

        if store_id:
            if store_id == 'c':  # connected
                # OR filter - the product is connected to store 1 OR store 2 OR store 3 OR so forth for all ebay stores
                # i.e. each of the products resulting from this query will be connected to at least one ebay store
                # SureDone uses parenthesis to indicate an OR filter
                per_store_filters = self.format_filters({
                    f'{self.get_ebay_prefix(store)}id': {'value': 0, 'relation': ':>'} for store in ebay_instance_ids
                })
                search_filter = f'{search_filter} ({per_store_filters})'
            elif store_id == 'n':  # non-connected
                in_store = safe_int(in_store)
                # Specific store
                if in_store:
                    store = get_object_or_404(EbayStore, id=in_store)
                    per_store_filters = self.format_filters({
                        'dropifiedconnectedstoreid': {'value': store.store_instance_id, 'relation': ':='},
                        f'{self.get_ebay_prefix(store.store_instance_id)}id': {'value': 0, 'relation': ':='},
                    })
                # All ebay stores
                else:
                    # AND filter - the product is not connected to store 1 AND store 2 AND store 3 AND so forth for all ebay stores
                    # i.e. none of the products resulting from this query will be connected to any ebay store
                    per_store_filters = self.format_filters({
                        f'{self.get_ebay_prefix(store)}id': {'value': 0, 'relation': ':='} for store in ebay_instance_ids
                    })
                search_filter = f'{search_filter} {per_store_filters}'
            else:
                store = get_object_or_404(EbayStore, id=store_id)
                # permissions.user_can_view(self.user, store)

                store_filter = self.format_filters({
                    f'{self.get_ebay_prefix(store.store_instance_id)}id': {'value': 0, 'relation': ':>'}
                })
                search_filter = f'{search_filter} {store_filter}'

        raw_products = self.get_all_products(search_filter)
        all_products = self.convert_to_ebay_product_models(raw_products)

        return all_products

    def get_ebay_products(self, store_id: str, in_store: str, post_per_page=25, sort=None, board=None, product_board=None, request=None):
        """
        Get all eBay products.

        :param product_board:
        :type product_board:
        :param store_id: eBay store id
        :type store_id: int
        :param in_store:
        :type in_store:
        :param post_per_page: Number of products to display per page
        :type post_per_page: int
        :param sort: Whether or not return the products sorted
        :type sort:
        :param board: Board name to filter the products by
        :type board:
        :param request: get filters from request to filter the products by
        :type request:
        :return:
        :rtype:
        """
        user_stores = self.user.profile.get_ebay_stores(flat=True)
        res = EbayProduct.objects.select_related('store') \
            .filter(user=self.user.models_user) \
            .filter(Q(store__in=user_stores) | Q(store=None))

        if store_id:
            if store_id == 'c':  # connected
                res = res.exclude(source_id=0)
            elif store_id == 'n':  # non-connected
                res = res.filter(source_id=0)

                in_store = safe_int(in_store)
                if in_store:
                    in_store = get_object_or_404(EbayStore, id=in_store)
                    res = res.filter(store=in_store)

                    permissions.user_can_view(self.user, in_store)
            else:
                store = get_object_or_404(EbayStore, id=store_id)
                res = res.filter(source_id__gt=0, store=store)

                permissions.user_can_view(self.user, store)

        if product_board in ['added', 'not_added']:
            board_list = self.user.models_user.ebayboard_set.all()
            if product_board == "added":
                res = res.filter(ebayboard__in=board_list)
            elif product_board == "not_added":
                res = res.exclude(ebayboard__in=board_list)

        if board:
            res = res.filter(ebayboard=board)
            permissions.user_can_view(self.user, get_object_or_404(EbayBoard, id=board))

        if request:
            res = products_filter(res, request.GET)

        if sort:
            if re.match(r'^-?(title|price)$', sort):
                res = res.order_by(sort)
            elif re.match(r'^-?(date)$', sort):
                date_sort = re.sub(r'date', r'created_at', sort)
                res = res.order_by(date_sort)

        return res

    def filter_by_connected(self, product):
        is_connected = product.is_connected
        return is_connected

    def format_error_messages_by_variant(self, errors: dict) -> str:
        return '\n\n'.join([f'<b>Variant #{i}</b>: {m}' for i, m in errors.items()])

    def combine_products_variants(self, products: list):
        """
        Get SureDone products where each variation is a separate product as an argument,
        and return a filtered list with only parent variants.

        :param products: All products with each variant as a separate product
        :type products: list
        :return: A list of unique products with variations merged into a single product
        :rtype: list
        """
        found_guids = []
        merged_products = []

        for product in products:
            sku = product.get('sku')
            guid = product.get('guid')
            if sku not in found_guids and guid == sku:
                found_guids.append(sku)
                merged_products.append(product)
        return merged_products

    def convert_to_ebay_product_models(self, raw_products: list):
        """
        Convert a list of dictionaries into a list of EbayProduct models

        :param raw_products: a list of dictionaries returned by SureDone API
        :type raw_products: list
        :return: a list of products converted into EbayProduct models
        :rtype: list
        """
        products = []

        for product_data in raw_products:
            guid = product_data.get('guid')
            if not guid:
                continue
            # 1. If the object is already saved into the db:
            try:
                found_product = EbayProduct.objects.get(guid=guid)

                # Compare the dates updated in SureDone
                date_updated_sd = self.parse_suredone_date(product_data.get('dateupdatedutc'))
                if not date_updated_sd:
                    date_updated_sd = self.parse_suredone_date(product_data.get('dateutc'))
                date_updated_db = arrow.get(found_product.sd_updated_at)

                # If the data in SureDone is newer, update the data in the db
                try:
                    if date_updated_sd > date_updated_db:
                        found_product = self.convert_to_ebay_product_model(product_data, product_to_update=found_product)
                        found_product.save()
                except TypeError:
                    found_product = self.convert_to_ebay_product_model(product_data, product_to_update=found_product)
                    found_product.save()

                products.append(found_product)

            # 2. If the object is not in the db yet:
            except EbayProduct.DoesNotExist:
                # Create and save a new product
                product = self.convert_to_ebay_product_model(product_data)
                product.save()

                products.append(product)

        return products

    def convert_to_ebay_product_model(self, sd_product_data: dict, product_to_update: EbayProduct = None,
                                      add_model_fields: dict = None):
        """
        Convert a SureDone product dictionary data into an EbayProduct model params,
        then create or update a product

        :param sd_product_data: a dictionary with all SureDone product fields
        :type sd_product_data: dict
        :param product_to_update: a product to update if it's already created
            if not passed then a new product gets initialized and returned
        :type product_to_update: EbayProduct
        :param add_model_fields: Additional fields to set on the Model
            where key is the field and value is the value to set it to
        :type add_model_fields: dict
        :return: an updated or created EbayProduct model
        :rtype: EbayProduct
        """
        if not add_model_fields:
            add_model_fields = {}

        guid = sd_product_data.get('guid')

        ebay_store_index = safe_int(sd_product_data.get('dropifiedconnectedstoreid'),
                                    default=sd_product_data.get('dropifiedconnectedstoreid'))
        if ebay_store_index is None or ebay_store_index == '':
            raise AttributeError(f'Connected store ID (dropifiedconnectedstoreid) is invalid for product with GUID {guid}')

        try:
            store = EbayStore.objects.get(store_instance_id=ebay_store_index, user=self.user.models_user)
        except EbayStore.DoesNotExist:
            store = None

        ebay_prefix = self.get_ebay_prefix(ebay_store_index)

        # Get product's eBay ID
        try:
            ebay_product_id = int(sd_product_data.get(f'{ebay_prefix}id'))
        except (ValueError, TypeError):
            ebay_product_id = sd_product_data.get(f'{ebay_prefix}id')

        # Get eBay category ID
        ebay_category_id = safe_int(sd_product_data.get(f'{ebay_prefix}catid'),
                                    sd_product_data.get(f'{ebay_prefix}catid'))

        # Get eBay site ID
        ebay_site_id = safe_int(sd_product_data.get(f'{ebay_prefix}siteid'), 0)

        # Get date product created
        product_created_at = sd_product_data.get('dateutc')
        # Get date product last updated
        product_updated_at = sd_product_data.get('dateupdatedutc')

        # Parse SureDone date strings
        if product_created_at:
            # Example of SureDone returned date: '2021-08-24 16:43:12'
            product_created_at = getattr(self.parse_suredone_date(product_created_at), 'datetime', None)

        if product_updated_at:
            product_updated_at = getattr(self.parse_suredone_date(product_updated_at), 'datetime', None)

        # Parse tags
        tags = sd_product_data.get('tags', '').replace('*', ',')

        # Get variants config
        variants_config = sd_product_data.get('variantsconfig', '[]')

        media_links = self.extract_media_from_product(sd_product_data)
        thumbnail_image = media_links[0] if len(media_links) > 0 else None

        model_params = {
            'user': self.user.models_user,
            'title': sd_product_data.get('title'),
            'price': sd_product_data.get('price'),
            'guid': sd_product_data.get('guid'),
            'sku': sd_product_data.get('sku'),
            'product_type': sd_product_data.get('producttype'),
            'tags': tags,
            'product_description': sd_product_data.get('longdescription'),
            # 'created_at': product_created_at,
            'sd_updated_at': product_updated_at if product_updated_at else product_created_at,
            'thumbnail_image': thumbnail_image,
            'media_links_data': json.dumps(media_links),
            'store': store,
            'sd_account': self.sd_account,
            'data': json.dumps(sd_product_data),
            'ebay_category_id': ebay_category_id,
            'ebay_store_index': ebay_store_index,
            'ebay_site_id': ebay_site_id,
            'source_id': ebay_product_id,
            'variants_config': variants_config,
            **add_model_fields
        }

        if product_to_update:
            for attr, value in model_params.items():
                setattr(product_to_update, attr, value)
            return product_to_update
        else:
            return EbayProduct(**model_params)

    def get_ebay_product_details(self, parent_guid: str, add_model_fields: dict = None, smart_board_sync=False) -> EbayProduct:
        """
        Get all product variants matching the passed GUID value as a SKU

        :param parent_guid: Parent variation product's GUID
        :type parent_guid: str
        :param add_model_fields: additional fields to set in the Model update or create step
        :type add_model_fields:
        :param smart_board_sync: Whether or not to perform a smart board sync when saving the product to the DB
        :type smart_board_sync: bool
        :return: a tuple with a list of EbayProduct models and a list of variants
        :rtype: tuple(list[EbayProduct], list)
        """
        if not add_model_fields:
            add_model_fields = {}

        # Get the parent product data using the SD edit API to include its attributes
        sd_product_data = self.api.get_item_by_guid(parent_guid)

        if sd_product_data and sd_product_data.get('guid'):
            attributes = list(sd_product_data.get('attributes', {}).values())
            variants_config = sd_product_data.get('variantsconfig', '[]')

            variants_config = safe_json(variants_config, []) if variants_config else []

            # Update or create the product in the Dropified db
            try:
                parent_product = EbayProduct.objects.get(guid=parent_guid)
                parent_product = self.convert_to_ebay_product_model(sd_product_data, parent_product, add_model_fields)
            except EbayProduct.DoesNotExist:
                parent_product = self.convert_to_ebay_product_model(sd_product_data, add_model_fields=add_model_fields)
            parent_product.save(smart_board_sync=smart_board_sync)

            ebay_prefix = self.get_ebay_prefix(parent_product.ebay_store_index)
            seen_variant_guids = [parent_guid]

            # Store the parent variant as the first variant
            self.update_or_create_product_variant(product_variant_data=sd_product_data, parent_product=parent_product,
                                                  ebay_prefix=ebay_prefix, variants_config=variants_config)
            # Extract relevant attributes/variants data
            for product_variant in attributes:
                seen_variant_guids.append(product_variant.get('guid'))
                self.update_or_create_product_variant(product_variant_data=product_variant, parent_product=parent_product,
                                                      ebay_prefix=ebay_prefix, variants_config=variants_config)

            # Find variants that were not returned by API and delete them
            removed_variants = EbayProductVariant.objects.filter(sku=parent_guid).exclude(guid__in=seen_variant_guids)
            if removed_variants.count() > 0:
                removed_variants.delete()

            return parent_product
        else:
            return None

    def update_or_create_product_variant(self, product_variant_data: dict, parent_product: EbayProduct,
                                         ebay_prefix: str, variants_config: list) -> EbayProductVariant:
        guid = product_variant_data.get('guid')
        sku = product_variant_data.get('sku')

        # SureDone field names as is to be stored as a stringified JSON
        extra_variant_params = {
            'compareatprice': product_variant_data.get('compareatprice', 'none'),
            'weight': product_variant_data.get('weight', ''),
            'stock': product_variant_data.get('stock'),
            'weightunit': product_variant_data.get('weightunit', 'lb'),
        }

        for variant in variants_config:
            key = variant.get('title', '').replace(' ', '').lower()
            if key:
                minified_key = self.sd_account.format_custom_field(variant.get('title', ''))
                extra_variant_params[minified_key] = product_variant_data.get(minified_key, '')
                extra_variant_params[key] = product_variant_data.get(key, extra_variant_params[minified_key])

        current_variant_params = {
            'parent_product': parent_product,
            'sku': sku,
            'variant_title': product_variant_data.get('varianttitle', ''),
            'price': product_variant_data.get('price', ''),
            'image': product_variant_data.get('media1'),
            'supplier_sku': product_variant_data.get('suppliersku', 'none'),
            'source_id': safe_int(product_variant_data.get(f'{ebay_prefix}id')),
            'variant_data': json.dumps(extra_variant_params),
        }

        variant, created = EbayProductVariant.objects.update_or_create(guid=guid, defaults=current_variant_params)
        return variant

    def get_ebay_prefix(self, ebay_store_index: int):
        """
        Compute ebay store prefix to use when getting corresponding SureDone product fields.
        Related SureDone Rules:
            1. All ebay-specific fields have a prefix "ebay", e.g. ebaycatid, ebay2catid
            2. The first ebay store instance doesn't have any index next to "ebay", e.g. ebaycatid
            3. All the remainining ebay store instances have their corresponding index next to "ebay,
                e.g. ebay2catid, ebay3catid, ebay4catid, etc.

        :param ebay_store_index: eBay store instance index
        :type ebay_store_index: int
        :return: computed prefix for the requested ebay store instance
        :rtype: str
        """
        if ebay_store_index == 1:
            ebay_index_prefix = 'ebay'
        else:
            ebay_index_prefix = f'ebay{ebay_store_index}'
        return ebay_index_prefix

    def search_categories(self, store_instance_index: int, search_term: str):
        """
        Search eBay categories by a product type keyword

        :param store_instance_index: ebay store instance index
        :type store_instance_index: int
        :param search_term: keyword to search for
        :type search_term: str
        :return: ebay categories matching the provided keyword
        :rtype:
        """
        return self.api.search_ebay_categories(store_instance_index, search_term)

    def get_category_specifics(self, site_id: int, cat_id: int):
        """
        Get required and recommended fields for an ebay category.

        :param site_id: ebay site ID
        :type site_id: int
        :param cat_id: ebay category ID
        :type cat_id: int
        :return:
        :rtype:
        """
        return self.api.get_ebay_specifics(site_id, cat_id)

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

    def get_ebay_orders(self, store: EbayStore, page=None, per_page=None, filters: dict = None):
        """
        Get all eBay orders.

        :param store: eBay store intance
        :type store: EbayStore
        :param page:
        :type page:
        :param per_page: Number of products to display per page
        :type per_page: int
        :param filters: Whether or not return the products sorted
        :type filters:
        :return:
        :rtype:
        """
        if filters is None:
            filters = {}
        filters['platform_type'] = 'ebay'
        sd_orders, total_products_count = self.get_orders_by_platform_type(store, filters, page=page, per_page=per_page)
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
                'value': 'ebay',
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

        sd_orders, total_products_count = self.get_all_orders(search_filters,
                                                              page=page,
                                                              sort_by=sort_by,
                                                              sort_order=sort_order)
        normalized_orders = []
        orders_cache = {}
        if isinstance(sd_orders, list):
            for order in sd_orders:
                norm_item = EbayOrderItem(self.user, store, order)

                for item in norm_item.items:
                    order_data_id = item.get('order_data_id')
                    order_data = item.get('order_data')
                    if order_data_id and order_data:
                        order_data = fix_order_data(self.user, order_data)
                        orders_cache[f'ebay_order_{order_data_id}'] = order_data

                normalized_orders.append(norm_item)

        caches['orders'].set_many(orders_cache, timeout=86400 if filters.get('bulk_queue') else 21600)

        return normalized_orders, total_products_count

    def get_tracking_orders(self, tracker_orders, per_page=50):
        filters = []
        for i in tracker_orders:
            filters.append(self.format_filters({'oid': {'value': i.order_id, 'relation': ':='}}))

        if not len(filters):
            return tracker_orders

        filters_str = ' '.join(filters)
        if len(filters) > 1:
            filters_str = f'({filters_str})'

        sd_orders, total_products_count = self.get_all_orders(filters=filters_str)

        orders = {}
        lines = {}

        for order in sd_orders:
            order['id'] = order['oid']
            orders[order['oid']] = order
            for line in order['items']:
                line['image'] = line.get('media', '')
                line['id'] = line.get('itemid')
                line['product_id'] = line['itemdetails']['product'].get('id')
                lines[f"{order['oid']}-{line['sku']}"] = line

        new_tracker_orders = []
        for tracked in tracker_orders:
            tracked.order = orders.get(f'{tracked.order_id}')
            tracked.line = lines.get(f'{tracked.order_id}-{tracked.line_id}')

            if tracked.line:
                fulfillment_status = (self.get_item_fulfillment_status(tracked.order, tracked.line_id) or '').lower()
                tracked.line['fulfillment_status'] = fulfillment_status

                if tracked.ebay_status != fulfillment_status:
                    tracked.ebay_status = fulfillment_status
                    tracked.save()

            new_tracker_orders.append(tracked)

        return new_tracker_orders

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

    def get_tracking_products(self, tracker_orders, per_page=50):
        ids = set([str(i.line_id) for i in tracker_orders])

        if not len(ids):
            return tracker_orders

        product_variants = EbayProductVariant.objects.filter(guid__in=ids)
        products_by_guid = {}
        for product in product_variants:
            products_by_guid[product.guid] = product

        new_tracker_orders = []
        for tracked in tracker_orders:
            tracked.product = products_by_guid.get(tracked.line_id)
            if tracked.product:
                if not tracked.line:
                    continue

                tracked.line['image'] = tracked.product.image
            new_tracker_orders.append(tracked)

        return new_tracker_orders

    def split_product(self, product: EbayProduct, split_factor: str):
        """
        Split an existing product on SureDone and push all changes to Dropified DB
        :param product: product for split
        :type product: EbayProduct
        :param split_factor:
        :type split_factor: str
        :return: SureDone's API response
        :rtype: JsonResponse
        """
        if not self.api:
            return

        sd_api_result = self.sd_split_product(product, split_factor)

        # If the SureDone returns no data, then the product was not successfully splitted
        if sd_api_result.get('api_response', {}).get('result') != 'success':
            return sd_api_result

        # If the SureDone returns data successfully, then update the products from SureDone in Dropified DB
        splitted_products = sd_api_result.pop('splitted_products')

        original_sku = product.sku
        original_parent_product = product.parsed
        original_product_variants = list(original_parent_product.get('attributes', {}).values())
        original_product_variants.append(original_parent_product)

        new_products = {}
        for splitted_product in splitted_products:
            product_id = splitted_product.get('id')
            new_sku = splitted_product['sku']
            new_products[new_sku] = new_products.get(new_sku, {})
            for original_product_variant in original_product_variants:
                if product_id != original_product_variant.get('id'):
                    continue

                original_product_variant['sku'] = new_sku
                original_product_variant['variantsconfig'] = splitted_product.get('variantsconfig')

                # create new data field for splitted products
                if original_product_variant['guid'] == new_sku:
                    if 'attributes' in new_products[new_sku].keys():
                        original_product_variant['attributes'] = new_products[new_sku]['attributes']
                    else:
                        original_product_variant['attributes'] = []
                    new_products[new_sku] = original_product_variant
                else:
                    if 'attributes' in new_products[new_sku].keys():
                        new_products[new_sku]['attributes'].append(original_product_variant)
                    else:
                        new_products[new_sku]['attributes'] = original_product_variant

                # update data on EbayProductVariant table of Dropified DB
                ebay_product_variant = EbayProductVariant.objects.get(guid=original_product_variant['guid'])
                ebay_product_variant.sku = new_sku
                ebay_product_variant.save()

        # update data on EbayProduct table of Dropified DB
        for guid, data in new_products.items():
            ebay_product = EbayProduct.objects.get(guid=original_sku)

            for splitted_product in splitted_products:
                if splitted_product['sku'] == guid:
                    ebay_product.variants_config = splitted_product['variantsconfig']
                    break

            if data['attributes']:
                data['attributes'] = {k + 1: v for k, v in enumerate(data['attributes'])}
            ebay_product.update_data(data)
            ebay_product.thumbnail_image = data.get('media1', '')

            if guid == original_sku:
                ebay_product.save()
            else:
                ebay_product.pk = None
                ebay_product.guid = guid
                ebay_product.sku = guid
                ebay_product.save()

        return sd_api_result

    def duplicate_product(self, product_data: dict, store: EbayStore):
        """
        Save a new (duplicated) product to SureDone.
        :param product_data:
        :type product_data: dict
        :param store:
        :type store: EbayStore
        :return:
        :rtype:
        """
        if not self.api:
            return

        # Prepare product_data for SureDone format
        variants = product_data.pop('attributes', {})
        sd_product_data = [product_data, *list(variants.values())]

        sd_api_result = self.sd_duplicate_product(sd_product_data)

        # If the product was not successfully posted
        if sd_api_result.get('api_response', {}).get('result') != 'success':
            return

        parent_guid = sd_api_result.get('parent_guid')

        # Fetch the product from SureDone and save the product if the product was successfully imported
        created_product = self.get_ebay_product_details(parent_guid)

        # If the SureDone returns no data, then the product did not get imported
        if not created_product or not isinstance(created_product, EbayProduct):
            return

        # Init the default supplier
        store_info = json.loads(product_data.get('store', {}))
        original_url = product_data.get('original_url', '')
        supplier = EbaySupplier.objects.create(
            store=store,
            product=created_product,
            product_guid=parent_guid,
            product_url=safe_str(original_url)[:512],
            supplier_name=store_info.get('name') if store_info else '',
            supplier_url=store_info.get('url') if store_info else '',
            is_default=True
        )
        created_product.set_default_supplier(supplier, commit=True)

        return sd_api_result

    def order_id_from_name(self, store, order_name, default=None):
        order_name = order_name.replace('#', '')
        if not order_name:
            return default

        sd_orders, sd_orders_count = self.get_all_orders(filters=f'{order_name}')

        if sd_orders_count and len(sd_orders):
            return [i.get('oid') for i in sd_orders]

        return default

    def parse_ebay_errors(self, api_error_message):
        api_ebay_errors_list = [error for error in api_error_message.split('Failure | ') if 'ErrorCode:' in error]

        parsed_ebay_errors_list = []

        if api_ebay_errors_list:
            for api_ebay_error in api_ebay_errors_list:
                api_ebay_error = api_ebay_error.replace(' | ', '\n')
                ebay_error_items = api_ebay_error.split('\n')
                ebay_error = {}
                for ebay_error_item in ebay_error_items:
                    if 'ErrorCode:' in ebay_error_item:
                        ebay_error["error_code"] = ebay_error_item.replace('ErrorCode:', '').strip()
                    if 'ShortMessage:' in ebay_error_item:
                        ebay_error["short_message"] = ebay_error_item.replace('ShortMessage:', '').strip()
                    if 'LongMessage:' in ebay_error_item:
                        ebay_error["long_message"] = ebay_error_item.replace('LongMessage:', '').strip()
                parsed_ebay_errors_list.append(ebay_error)
        else:
            parsed_ebay_errors_list.append({'short_message': api_error_message, 'long_message': api_error_message})

        return parsed_ebay_errors_list

    def start_new_products_import_job(self, store: EbayStore):
        resp = self.api.post_new_ebay_products_import_job(store.instance_prefix)
        resp_body = resp.json()
        resp.raise_for_status()

        return resp_body

    def get_import_products_status(self, store: EbayStore):
        resp = self.api.get_import_options(store_prefix=store.instance_prefix)
        resp_body = resp.json()
        resp.raise_for_status()

        store_options = safe_json(resp_body.get(f'{store.instance_prefix}_attribute_mapping', '{}'), {})
        last_imported_file = store_options.get('last_import_file_actions')
        import_products_set = store_options.get('import_products_set')

        if import_products_set == 'on':
            status = 'Import in Progress'
        else:
            status = 'No past imports found. Start a new import job to import and update products.'

        last_updated = None
        if last_imported_file and import_products_set != 'on':
            status = 'Finished'
            # Example filename: 20220418-220226-36-ebay2-match.csv
            date_parts = last_imported_file.split('-')
            last_updated = arrow.get(f'{date_parts[0]} {date_parts[1]}', 'YYYYMMDD HHmmss').datetime

        return {'status': status, 'last_updated': last_updated}

    def get_import_file_url(self, store: EbayStore):
        resp = self.api.get_import_options(store_prefix=store.instance_prefix)
        resp_body = resp.json()
        resp.raise_for_status()

        store_options = safe_json(resp_body.get(f'{store.instance_prefix}_attribute_mapping', '{}'), {})
        last_imported_file = store_options.get('last_import_file_actions')

        # Get the file link
        resp = self.api.get_import_file_download_link(filename=last_imported_file)
        resp_body = resp.json()
        resp.raise_for_status()

        return resp_body.get('url')

    def get_import_products(self, store: EbayStore, user, page: int = 1, limit: int = 20):
        url = self.get_import_file_url(store)
        next_page = False
        result = dict()

        if url:
            resp = requests.get(url)
            lines = resp.text.splitlines()
            reader = csv.reader(lines)

            header = list(next(reader))
            sku_field_index = header.index('sku')

            current_index = 0  # Index among products with unique sku values

            start_index = limit * (page - 1)
            limit_index = start_index + limit

            for i, row in enumerate(reader):
                row_sku = row[sku_field_index]
                if row_sku in result:
                    result[row_sku]['variants_count'] += 1
                    continue

                # If the current index reached the next page
                if current_index >= limit_index:
                    next_page = True
                    break

                # If the current index reached the current page
                if current_index >= start_index:
                    value = {header[index]: value for index, value in enumerate(row)}
                    try:
                        product_type = value.get(f'{store.instance_prefix}catname', '').split(':')[-1]
                    except:
                        product_type = ''

                    result[row_sku] = {
                        'image': value.get('media1', ''),
                        'title': value.get('title', ''),
                        'price': f'{value.get("price", "")}',
                        'ebay_link': value.get(f'{store.instance_prefix}url', ''),
                        'csv_index_position': i,
                        'id': row_sku,
                        'product_link': None,
                        'status': 'non-connected',
                        'variants_count': 1,
                        'product_type': product_type,
                    }

                current_index += 1

            products_by_guid = EbayProduct.objects.filter(guid__in=result.keys(), user=user.models_user)

            for product in products_by_guid:
                supplier_name = ''
                original_url = ''
                if product.have_supplier:
                    supplier_name = product.default_supplier.supplier_name
                    original_url = product.default_supplier.product_url

                result[product.guid].update({
                    'product_link': reverse('ebay:product_detail', args=[store.id, product.guid]),
                    'status': 'connected',
                    'supplier_name': supplier_name,
                    'original_url': original_url,
                })

        return {'products': list(result.values()), 'next': next_page}

    def import_product_base(self, store: EbayStore, action: str, csv_position: int, product_variants_count: int):
        url = self.get_import_file_url(store)
        if url:
            resp = requests.get(url)
            lines = resp.text.splitlines()
            reader = list(csv.reader(lines))

            # Pad rows in case some trailing empty column values are missing
            reader = list(zip(*itertools.zip_longest(*reader, fillvalue='')))

            header = list(reader.pop(0))
            selected_rows = reader[csv_position:csv_position + product_variants_count]
            selected_rows = [list(row) for row in selected_rows]

            if len(selected_rows) == 0:
                raise ValueError('No import data was found for this product.', resp)

            # Handle images
            media_indices = [header.index(f'media{i}') for i in range(1, 11)]
            all_images = [selected_rows[0][i] for i in media_indices if selected_rows[0][i]]
            all_images.extend(selected_rows[0][header.index('mediax')].split('*'))

            # Construct variantsconfig and varianttitle
            header.append('varianttitle')
            variants = {}
            if len(selected_rows) == 1:
                selected_rows[0].append('')
            else:
                variations_index = header.index(f'{store.instance_prefix}variations')
                for index, row in enumerate(selected_rows):
                    variations_from_csv = safe_json(row[variations_index], row[variations_index])
                    if not isinstance(variations_from_csv, dict):
                        continue

                    row.append(' / '.join(variations_from_csv.get('specifics', {}).values()))
                    for key, value in variations_from_csv.get('specifics', {}).items():
                        if key in variants:
                            variants[key].append(value)
                        else:
                            variants[key] = [value]

            variants_config = [{'title': title, 'values': values} for title, values in variants.items()]
            common_values_to_add = {
                'dropifiedconnectedstoretype': 'ebay',
                'dropifiedconnectedstoreid': str(store.store_instance_id),
                'allimages': json.dumps(all_images),
                'variantsconfig': json.dumps(variants_config),
            }
            header.extend(common_values_to_add.keys())
            action_index = header.index('action')

            for row in selected_rows:
                row.extend(common_values_to_add.values())
                # Update the action type in case it was "Add" initially
                row[action_index] = action

            selected_rows.insert(0, header)
            return self.api.post_imported_products(selected_rows)
        else:
            raise ValueError('No import data was found.')

    def import_product_from_csv(self, store, product_guid, csv_position, product_variants_count,
                                supplier_url, vendor_name, vendor_url):
        resp = self.import_product_base(
            store=store,
            action='add',
            csv_position=csv_position,
            product_variants_count=product_variants_count,
        )

        resp_body = resp.json()
        resp.raise_for_status()

        # Fetch SureDone updates and update the DB
        updated_product = self.get_ebay_product_details(product_guid, smart_board_sync=True)

        if not updated_product:
            raise Exception('Failed to get product details.', updated_product)

        product_supplier = EbaySupplier.objects.create(
            store=store,
            product=updated_product,
            product_guid=product_guid,
            product_url=supplier_url,
            supplier_name=vendor_name,
            supplier_url=vendor_url,
            is_default=True
        )
        updated_product.set_default_supplier(product_supplier, commit=True)
        return resp_body

    def update_product_from_import_csv(self, product, csv_position, product_variants_count):
        resp = self.import_product_base(
            store=product.store,
            action='edit',
            csv_position=csv_position,
            product_variants_count=product_variants_count,
        )

        resp_body = resp.json()
        resp.raise_for_status()

        for i in range(1, resp_body.get('actions') + 1):
            if resp_body.get(f'{i}', {}).get('result') != 'success':
                raise Exception('Failed to sync a product. Please try submitting a new import job.')

        # Fetch SureDone updates and update the DB
        updated_product = self.get_ebay_product_details(product.guid, smart_board_sync=True)

        if not updated_product:
            raise Exception('Failed to get product details.', updated_product)

        return resp_body


class EbayOrderUpdater:
    def __init__(self, user=None, store: EbayStore = None, order_id: int = None):
        self.utils = None
        if user:
            self.utils = EbayUtils(user)
        self.user = user
        self.store = store
        self.order_id = order_id
        self.notes = []

    def add_note(self, n):
        self.notes.append(n)

    def mark_as_ordered_note(self, line_id: str, source_id: int, track: EbayOrderTrack):
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
            self.add_ebay_order_note(self.order_id, new_note)

    def delay_save(self, countdown=None):
        from ebay_core.tasks import order_save_changes

        order_save_changes.apply_async(
            args=[self.toJSON()],
            countdown=countdown
        )

    def toJSON(self):
        return json.dumps({
            "notes": self.notes,
            "order": self.order_id,
            "store": self.store.id,
            "user": self.user.models_user.id,
        }, sort_keys=True, indent=4)

    def fromJSON(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        self.store = EbayStore.objects.get(id=data.get('store'))
        self.order_id = data.get('order')
        self.user = User.objects.get(id=data.get('user'))
        if self.user:
            self.utils = EbayUtils(self.user)
        self.notes = data.get('notes')

    def add_ebay_order_note(self, order_id: int, note: str):
        if not self.utils:
            raise AttributeError('Error saving eBay order note: No user was provided.')

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


class EbayListPaginator(SimplePaginator):
    def page(self, number):
        number = self.validate_number(number)
        self.current_page = number
        params = {'page': number, 'per_page': self.per_page}

        # `self.object_list` is a `EbayOrderListQuery` instance
        items = list(self.object_list.update_params(params).items())

        return self._get_page(items, number, self)


class EbayOrderListQuery(object):
    def __init__(self, user, store, params=None):
        self._user = user
        self._store = store
        self._utils = EbayUtils(self._user)

        self._items = []
        self._total_count = 0
        self._params = {
            'page': 1,
            'per_page': 20
        }

        if params:
            self._params.update(params)

        self.fetch_items()

    def fetch_items(self):
        self._items, self._total_count = self._utils.get_ebay_orders(self._store,
                                                                     filters=self._params,
                                                                     page=self._params.get('page'),
                                                                     per_page=self._params.get('per_page'))
        return self._items

    def items(self):
        return self._items if self._items else self.fetch_items()

    def count(self):
        return self._total_count

    def update_params(self, update):
        new_params = {**self._params, **update}
        if new_params != self._params:
            self._items = []
            self._params = new_params
            self.fetch_items()

        return self


class EbayOrderItem:
    def __init__(self, user, store: EbayStore, sd_order_data: dict):
        self.user = user
        utils = EbayUtils(user)
        self.store = store
        self.suredone_data = sd_order_data

        self.oid = sd_order_data.get('oid')
        self.id = self.oid

        all_items = sd_order_data.get('items', [])
        all_shipments = sd_order_data.get('shipments', [])
        product_ids = []
        for item in all_items:
            converted_ebay_id = safe_int(item.get('itemdetails', {}).get('item-id'), default=None)
            if converted_ebay_id is not None:
                product_ids.append({'sku': item.get('sku'), 'ebay-id': converted_ebay_id})

        product_variants_by_guids = self.get_products_by_guids(product_ids)
        order_tracks_by_order_id = self.get_order_track_by_item([self.oid])

        self.connected_lines = len(product_variants_by_guids)
        self.placed_orders = 0
        self.lines_count = len(all_items)

        # Calculate ebay order ID, sales record number and order url link
        order_meta_data = sd_order_data.get('meta', {}).get('raw', {}).get('order')
        if order_meta_data and isinstance(order_meta_data, dict):
            self.ebay_order_id = order_meta_data.get('OrderID')
            self.srn = order_meta_data.get('SalesRecord')  # eBay sales record number
            if self.ebay_order_id:
                self.order_url = self.get_ebay_order_link(self.ebay_order_id, self.srn)

        self.date = parse_suredone_date(sd_order_data.get('dateutc'))
        self.fulfillment_status = ''
        self.date_paid = parse_suredone_date(sd_order_data.get('paymentdate'))
        self.status = sd_order_data.get('status')
        self.partially_ordered = False
        self.tracked_lines = 0
        self.supplier_types = set()
        self.number = self.ebay_order_id
        self.total = sd_order_data.get('total')
        self.notes = sd_order_data.get('internalnotes')
        self.last_note = list(self.notes.values())[-1] if self.notes else ''
        self.store = self.store

        sd_shipping_data = sd_order_data.get('shipping')
        self.has_shipping_address = False
        if sd_shipping_data:
            self.shipping = {
                'first_name': sd_shipping_data.get('firstname'),
                'last_name': sd_shipping_data.get('lastname'),
                'company': sd_shipping_data.get('company'),
                'address_1': sd_shipping_data.get('street1'),
                'address_2': sd_shipping_data.get('street2'),
                'city': sd_shipping_data.get('city'),
                'state': sd_shipping_data.get('stateprovince'),
                'postcode': sd_shipping_data.get('postalcode'),
                'country': sd_shipping_data.get('country'),
            }
            self.has_shipping_address = any(self.shipping.values())
        sd_billing_data = sd_order_data.get('billing')
        if sd_billing_data:
            self.billing = {
                'first_name': sd_billing_data.get('firstname'),
                'last_name': sd_billing_data.get('lastname'),
                'company': sd_billing_data.get('company'),
                'address_1': sd_billing_data.get('street1'),
                'address_2': sd_billing_data.get('street2'),
                'city': sd_billing_data.get('city'),
                'state': sd_billing_data.get('stateprovince'),
                'postcode': sd_billing_data.get('postalcode'),
                'country': sd_billing_data.get('country'),
                'phone': sd_billing_data.get('phone'),
                'email': sd_order_data.get('email'),
            }

        order_paid = sd_order_data.get('paymentstatus') == 'COMPLETE'
        self.items = []
        fulfillment_per_sku = self.get_fulfillment_status_per_sku(all_shipments)

        for item in all_items:
            ebay_product_id = safe_int(item.get('itemdetails').get('item-id'), default=None)
            product_variant = product_variants_by_guids.get(item.get('sku'))
            supplier = supplier_type = None
            is_pls = False
            item_id = item.get('sku')
            attributes = ''

            if product_variant:
                var_attributes_keys = self.get_attribute_keys_from_var_config(product_variant)
                var_attributes_keys = utils.convert_to_default_and_custom_fields(var_attributes_keys)
                if var_attributes_keys:
                    var_data = product_variant.parsed_variant_data
                    attributes = [var_data.get(key) for key in var_attributes_keys if var_data.get(key)]
                    attributes = ', '.join(attributes)
                supplier = self.get_product_supplier(product_variant)
                if supplier:
                    is_pls = supplier.is_pls
                    get_supplier_type = getattr(supplier, 'supplier_type', None)
                    if get_supplier_type is not None:
                        supplier_type = get_supplier_type()
                        self.supplier_types.add(supplier_type)

            # Get Order track
            key = format_order_tracking_key(self.id, item_id)
            order_track = order_tracks_by_order_id.get(key)
            if order_track:
                self.tracked_lines += 1

            current_item = {
                'is_bundle': False,
                'id': item_id,
                'title': item.get('title'),
                'supplier_type': supplier_type,
                'product_id': ebay_product_id,
                'is_paid': order_paid,
                'is_pls': is_pls,
                'fulfillment_status': 'Unfulfilled',
                'image': item.get('media', ''),
                'attributes': attributes,
                'quantity': safe_int(item.get('quantity')),
                'price': item.get('price'),
                'product': product_variant,
                'supplier': supplier,
                'order_track': order_track,
            }

            self.update_placed_orders(current_item, fulfillment_per_sku)

            if supplier:
                # Calculate order data
                order_data = self.get_order_data(current_item, product_variant, supplier)
                order_data.update({
                    'products': [],
                    'is_bundle': False,
                    'is_refunded': False,  # TODO: where can this calculated from?
                    'weight': item.get('weight', None),
                })
                if product_variant:
                    order_data['variant'] = self.get_order_data_variant(product_variant)

                country_code = self.shipping.get('country') or self.billing.get('country')
                shippping_method = self.get_item_shipping_method(product_variant, current_item, country_code)
                current_item.update({
                    'order_data_id': order_data['id'],
                    'order_data': order_data,
                    'shippping_method': shippping_method,
                })

                if supplier.is_pls and supplier.user_supplement:
                    weight = supplier.user_supplement.get_weight(safe_int(item.get('quantity')))
                    order_data.update({
                        'weight': weight,
                    })

            self.items.append(current_item)

        if self.tracked_lines != 0 and self.tracked_lines < self.lines_count and \
                self.placed_orders < self.lines_count:
            self.partially_ordered = True

    def __getitem__(self, key):
        if isinstance(key, str) and hasattr(self, key):
            return getattr(self, key)

        raise IndexError('Index out of range')

    def get(self, key, default=None):
        if hasattr(self, key):
            return getattr(self, key)

        return default

    def get_fulfillment_status_per_sku(self, shipments: dict):
        result = {}
        for shipment_info in shipments:
            try:
                shipment_items = shipment_info.get('shipdetails', {}).get('items')
            except AttributeError:
                continue
            if not isinstance(shipment_items, list):
                continue
            skus = [x.get('sku') for x in shipment_items if 'sku' in x]
            for sku in skus:
                if sku in result:
                    result[sku].append(shipment_info)
                else:
                    result[sku] = [shipment_info]
        return result

    def get_attribute_keys_from_var_config(self, product_variant: EbayProductVariant) -> list:
        variants_config = product_variant.parent_product.variants_config_parsed
        var_attributes_keys = []
        if variants_config:
            var_attributes_keys = [i.get('title') for i in variants_config]
        return var_attributes_keys

    def get_order_data(self, item: dict, product: EbayProductVariant, supplier: EbaySupplier):
        store = self.store
        models_user = self.user.models_user
        aliexpress_fix_address = models_user.get_config('aliexpress_fix_address', True)
        aliexpress_fix_city = models_user.get_config('aliexpress_fix_city', True)
        german_umlauts = models_user.get_config('_use_german_umlauts', False)

        country = self.shipping.get('country') or self.billing.get('country')

        shipping_address = sd_customer_address(
            self.shipping,
            self.billing.get('phone'),
            aliexpress_fix=aliexpress_fix_address and supplier and supplier.is_aliexpress,
            aliexpress_fix_city=aliexpress_fix_city,
            german_umlauts=german_umlauts,
            shipstation_fix=supplier.is_pls if supplier else False)

        return {
            'id': f'{store.id}_{self.id}_{item["id"]}',
            'order_name': self.ebay_order_id,
            'title': item['title'],
            'quantity': item['quantity'],
            'shipping_address': shipping_address,
            'order_id': self.id,
            'line_id': item['id'],
            'product_id': product.id,
            'product_source_id': product.source_id,
            'source_id': supplier.get_source_id() if supplier else None,
            'supplier_id': supplier.get_store_id() if supplier else None,
            'supplier_type': supplier.supplier_type() if supplier else None,
            'total': safe_float(item['price'], 0.0),
            'store': store.id,
            'order': {
                'phone': {
                    'number': self.billing.get('phone'),
                    'country': country,
                },
                'note': models_user.get_config('order_custom_note'),
                'epacket': bool(models_user.get_config('epacket_shipping')),
                'aliexpress_shipping_method': models_user.get_config('aliexpress_shipping_method'),
                'auto_mark': bool(models_user.get_config('auto_ordered_mark', True)),  # Auto mark as Ordered
            },
        }

    def get_order_data_variant(self, product_variant: EbayProductVariant):
        mapped = product_variant.parent_product.get_variant_mapping(name=product_variant.guid,
                                                                    for_extension=True,
                                                                    mapping_supplier=True)
        if mapped:
            return mapped

        variants = []
        var_attributes_keys = [SureDoneAccount.minimize_custom_field_name(i)
                               for i in self.get_attribute_keys_from_var_config(product_variant)]
        sku_values = product_variant.supplier_sku.split(';')
        for i, var_key in enumerate(var_attributes_keys):
            var_data = product_variant.parsed_variant_data
            variants.append({
                'title': var_data.get(var_key),
                'image': product_variant.image,
                'sku': sku_values[i] if len(sku_values) > i else None
            })
        return variants

    def get_item_shipping_method(self, product_variant: EbayProductVariant, item: dict, country_code: str):
        if item.get('supplier'):
            return product_variant.parent_product.get_shipping_for_variant(supplier_id=item['supplier'].id,
                                                                           variant_id=product_variant.guid,
                                                                           country_code=country_code)

    def get_order_ids(self, orders: list):
        return [safe_int(order.get('oid')) for order in orders]

    def get_products_by_source_ids(self, product_ids: list):
        product_by_source_id = {}
        store = self.store
        for product in EbayProduct.objects.filter(store=store, source_id__in=product_ids):
            product_by_source_id[product.source_id] = product

        return product_by_source_id

    def get_products_by_guids(self, product_ids_data: list):
        products_by_guids = {}
        store = self.store

        for product_var_ids in product_ids_data:
            sku = product_var_ids.get('sku')

            # use ebay_id if only active products should be included
            # ebay_id = product_var_ids.get('ebay-id')

            try:
                product_var = EbayProductVariant.objects.get(guid=sku, parent_product__store=store)
            except EbayProductVariant.DoesNotExist:
                continue

            products_by_guids[product_var.guid] = product_var

        return products_by_guids

    def get_order_track_by_item(self, order_ids: list):
        track_by_item = {}
        store = self.store

        for track in EbayOrderTrack.objects.filter(store=store, order_id__in=order_ids):
            key = format_order_tracking_key(track.order_id, track.line_id)
            track_by_item[key] = track

        return track_by_item

    def update_placed_orders(self, item, fulfillment_per_sku):
        if item['id'] in fulfillment_per_sku:
            item['fulfillment_status'] = 'Fulfilled'
            self.placed_orders += 1

        if self.placed_orders == self.lines_count:
            self.fulfillment_status = 'Fulfilled'
        elif self.placed_orders > 0 and self.placed_orders < self.lines_count:
            self.fulfillment_status = 'Partially Fulfilled'
        else:
            self.fulfillment_status = None

    def get_ebay_order_link(self, order_id: str, srn: str):
        return f'{self.store.get_store_url()}/sh/ord/details?orderid={order_id}&srn={srn}'

    def get_product_supplier(self, product):
        if product.has_supplier:
            return product.variant_specific_supplier

    def format_ebay_order_track_key(self, order_id: int, line_id: str, product_id: str):
        return f'{order_id}_{line_id}_{product_id}'


@add_to_class(UserProfile, 'sync_ebay_stores')
def user_sync_ebay_stores(self):
    if self.user:
        EbayUtils(self.user).sync_ebay_stores()


def get_store_from_request(request):
    store = None
    user = request.user
    stores = user.profile.get_ebay_stores()

    store_id = request.GET.get('store')
    if store_id:
        store = get_object_or_404(stores, id=safe_int(store_id))

    if store:
        permissions.user_can_view(user, store)
        request.session['last_store'] = store.id
    else:
        try:
            if 'last_store' in request.session:
                store = stores.get(id=request.session['last_store'])
                permissions.user_can_view(user, store)

        except (PermissionDenied, EbayStore.DoesNotExist):
            store = None

    if not store:
        store = stores.first()

    return store


def get_fulfillment_meta(shipping_carrier_name, tracking_number, item_sku, date_shipped):
    return {
        'shipcarrier': shipping_carrier_name,
        'shiptracking': tracking_number,
        'shipdate': date_shipped,
        'shipdetails': {
            'items': [{'sku': item_sku}]
        }
    }


def format_order_tracking_key(order_id: str, line_id: str):
    return f'{order_id}_{line_id}'


def smart_board_by_product(user, product):
    product_info = {
        'title': product.title,
        'tags': product.tags,
        'type': product.product_type,
    }

    for k, v in list(product_info.items()):
        if v:
            product_info[k] = [i.lower().strip() for i in v.split(',')]
        else:
            product_info[k] = []

    for board in user.ebayboard_set.all():
        try:
            config = json.loads(board.config)
        except:
            continue

        product_added = False
        for config_key in ['title', 'tags', 'type']:
            if product_added:
                break

            if not len(config.get(config_key, '')) or not product_info[config_key]:
                continue

            for config_value in config.get(config_key, '').split(','):
                curr_value = config_value.lower().strip()
                if any([curr_value in k for k in product_info[config_key]]):
                    board.products.add(product)
                    product_added = True
                    break

        if product_added:
            board.save()


def get_ebay_site_id_options():
    return [
        (1, 'US'),
        (2, 'Canada'),
        (3, 'UK'),
        (15, 'Australia'),
        (16, 'Austria'),
        (23, 'Belgium (French)'),
        (71, 'France'),
        (77, 'Germany'),
        (100, 'eBay Motors'),
        (101, 'Italy'),
        (123, 'Belgium (Dutch)'),
        (146, 'Netherlands'),
        (186, 'Spain'),
        (193, 'Switzerland'),
        (201, 'Hong Kong'),
        (203, 'India'),
        (205, 'Ireland'),
        (207, 'Malaysia'),
        (210, 'Canada (French)'),
        (211, 'Philippines'),
        (212, 'Poland'),
        (216, 'Singapore'),
        (218, 'Sweden'),
    ]


def get_ebay_store_specific_currency_options():
    return [
        ('', 'Select Currency...', ''),
        ('USD', 'US Dollar', '$'),
        ('CAD', 'Canadian Dollar', 'Can$'),
        ('GBP', 'British Pound', '£'),
        ('AUD', 'Australian Dollar', 'A$'),
        ('EUR', 'Euro', '€'),
        ('CHF', 'Swiss Franc', 'fr'),
        ('CNY', 'Chinese Renminbi', '¥'),
        ('HKD', 'Hong Kong Dollar', 'HK$'),
        ('PHP', 'Philippines Peso', '₱'),
        ('PLN', 'Polish Zloty', 'zł'),
        ('SEK', 'Sweden Krona', 'kr'),
        ('SGD', 'Singapore Dollar', 'S$'),
        ('TWD', 'Taiwanese Dollar', 'NT$'),
        ('MYR', 'Malaysian Ringgit', 'RM')
    ]


def get_ebay_currencies_list():
    return [
        ('USD', 'US Dollar'),
        ('GBP', 'British Pound'),
        ('AUD', 'Australian Dollar'),
        ('CAD', 'Canadian Dollar'),
        ('CNY', 'Chinese Renminbi'),
        ('MXN', 'Mexican Peso'),
    ]


def cache_fulfillment_data(order_tracks, orders_max=None, output=None):
    """
    Caches order data of given `EbayOrderTrack` instances
    """
    order_tracks = order_tracks[:orders_max] if orders_max else order_tracks
    sd_all_orders = []
    stores = set()
    users = set()

    for order_track in order_tracks:
        stores.add(order_track.store)
        users.add(order_track.user)

    for user in users:
        user_order_tracks = [order_track for order_track in order_tracks if order_track.user_id == user.id]
        sd_all_orders += EbayUtils(user).get_tracking_orders(user_order_tracks)

    cache_data = {}
    counter = 0
    for store in stores:
        try:
            counter += 1
            # get all orders from the store
            sd_orders = [sd_order.order for sd_order in sd_all_orders if sd_order.store_id == store.id]

            if output:
                output.write(f'[{counter}/{len(stores)}] eBay Cache: {len(sd_orders)} Orders for store: {store.title}:{store.id}')

            for sd_order in sd_orders:
                country = sd_order['shipping']['country'] or sd_order['billing']['country']
                cache_data[f"ebay_auto_country_{store.id}_{sd_order['oid']}"] = country

                for item in sd_order.get('items', []):
                    cache_key = f"ebay_auto_fulfilled_order_{store.id}_{sd_order['oid']}_{item['sku']}"
                    cache_data[cache_key] = (item.get('fulfillment_status') == 'fulfilled')

        except Exception as e:
            if output:
                output.write(f'    eBay Cache Error for {store.title}:{store.id}')
                output.write(f'    HTTP Code: {http_excption_status_code(e)} Error: {http_exception_response(e)}')

            capture_exception(extra=http_exception_response(e))

    cache.set_many(cache_data, timeout=3600)

    return list(cache_data.keys())


def cached_order_line_fulfillment_status(order_track):
    return cache.get(f'ebay_auto_fulfilled_order_{order_track.store.id}_{order_track.order_id}_{order_track.line_id}')


def order_track_fulfillment(order_track, user_config=None):
    tracking_number = order_track.source_tracking

    # Keys are set by `ebay_core.utils.cache_fulfillment_data`
    country = cache.get(f'ebay_auto_country_{order_track.store_id}_{order_track.order_id}')

    shipping_carrier_name = leadgalaxy_utils.shipping_carrier(tracking_number)
    if country and country == 'US':
        if leadgalaxy_utils.is_chinese_carrier(tracking_number) or leadgalaxy_utils.shipping_carrier(tracking_number) == 'USPS':
            shipping_carrier_name = 'USPS'

    shipping_carrier_name = 'AfterShip' if not shipping_carrier_name else shipping_carrier_name
    date_shipped = arrow.get(timezone.now()).format('MM/DD/YYYY')

    meta_data = get_fulfillment_meta(
        shipping_carrier_name,
        tracking_number,
        order_track.line_id,
        date_shipped
    )

    data = {
        'shipments': [meta_data],
        'shippingstatus': 'COMPLETE',
    }

    return data
