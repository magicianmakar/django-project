import arrow
import json
import re
from requests.exceptions import HTTPError

from django.core.cache import caches
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404

# import urllib.parse
# from django.conf import settings
from google_core.models import GoogleBoard, GoogleOrderTrack, GoogleProduct, GoogleProductVariant, GoogleStore, GoogleSupplier
from leadgalaxy.models import UserProfile
from lib.exceptions import capture_exception
from shopified_core import permissions
from shopified_core.decorators import add_to_class
from shopified_core.paginators import SimplePaginator
from shopified_core.utils import fix_order_data, products_filter, safe_float, safe_int, safe_json, safe_str
from suredone_core.models import SureDoneAccount
from suredone_core.utils import SureDoneOrderUpdater, SureDoneUtils, parse_suredone_date, sd_customer_address


class GoogleUtils(SureDoneUtils):
    def get_active_instances(self):
        active_instances = []
        plugin_settings = safe_json(self.api.get_all_account_options().get('plugin_settings', {})).get('register', {})

        if 'google' in plugin_settings.get('context', {}):
            active_instances.append(0)

        try:
            additional_google_channels = plugin_settings.get('instance', {}).get('google', {}).values()
        except AttributeError:
            additional_google_channels = []

        active_instances.extend([i.get('instance') for i in additional_google_channels])
        return active_instances

    def find_next_instance_to_authorize(self):
        # google_statuses = self.get_store_statuses_by_platform('google')
        # next_instance_id = max([x.get('instance', -1) for x in google_statuses]) + 1
        active_instances = self.get_active_instances()
        next_instance_id = 0

        if len(active_instances):
            next_instance_id = max(active_instances) + 1

        # SureDone doesn't have any instances with an id of 1, ids can be either 0 or 2, 3, 4, etc.
        return 2 if next_instance_id == 1 else next_instance_id

    def create_new_google_store_instance(self, instance_id: int):
        resp = self.api.add_new_google_instance(instance_id)
        resp.raise_for_status()

        # Example successful response:
        # {"results":{"successful":{"code":1,"message":"Successfully created google5"}}}
        results = resp.json().get('results', {})
        message_success = results.get('successful', {}).get('message')

        # Handle errors if not successful
        if not message_success:
            # Example failed response:
            # {"results":{"failed":{"0":{"message":"Failed to create google5: google5 already exists"}}}}
            message_error = results.get('failed', {}).get('message', f'SureDone error for instance {instance_id}')
            raise HTTPError(message_error)

        message_success = message_success.split(' ')
        instance_created = instance_id
        if len(message_success) and 'google' in message_success[-1]:
            instance_created = message_success[-1].strip().replace('google', '')
            instance_created = safe_int(instance_created if len(instance_created) else 0)

        return instance_created

    def get_auth_url(self, instance_id: int):
        resp = self.api.get_google_channel_auth_url(instance_id)
        resp.raise_for_status()

        # Example successful response:
        # {"results":{"successful":{"code":1,"message":"Successfully created google5"}}}
        results = resp.json().get('results', {})
        successful_results = results.get('successful', {})
        message_success = successful_results.get('message')

        # Handle errors if not successful
        if not message_success:
            # Example failed response:
            # {"results":{"failed":{"0":{"message":"Failed to create google5: google5 already exists"}}}}
            message_error = results.get('failed', {}).get('message', f'SureDone error for instance {instance_id}')
            raise HTTPError(message_error)

        # Replace instance id uri path to param
        auth_url = successful_results.get('auth_url')

        if auth_url:
            pass
            # TODO: uncomment once SureDone supports dynamic redirect URL
            # subdomain = 'dev' if settings.DEBUG else 'app'
            # redirect_url = urllib.parse.quote_plus(f'{settings.APP_URL}/google/accept-auth')
            # state = re.search('state=.+&', auth_url).group(0).replace('&', '')
            # new_state = json.dumps({'code': state.replace('state=', ''), 'instance': instance_id})
            # auth_url = re.sub(r'https://*.?/google/accept-auth(/\d+)?', redirect_url, auth_url)
            # auth_url = auth_url.replace(state, f'state={new_state}')

        return auth_url

    def get_google_shop_options(self, instance_id):
        resp = self.api.get_google_channel_auth_url(instance_id=instance_id)
        resp.raise_for_status()

        commerce_managers = resp.json().get('results', {}).get('successful', {}).get('commerce_managers', [])
        return commerce_managers

    def onboard_google_instance(self, cms_id, instance_id):
        resp = self.api.post_google_onboard_instance(cms_id=cms_id, instance_id=instance_id)
        resp.raise_for_status()

        return resp.json().get('results', {})

    def sync_google_stores(self, use_cached=False):
        if not self.api:
            return

        # 1. Get all suredone options
        all_options_data = self.get_all_user_options(verify_custom_fields=True, use_cached=use_cached)
        if not isinstance(all_options_data, dict):
            return

        # 2. Extract a list of all channel settings
        plugin_settings = safe_json(all_options_data.pop('plugin_settings', '{}')).get('register', {})

        # 3. Sync all store instances
        # 3.1. Check the first and default google instance
        if 'google' in plugin_settings.get('context', {}):
            self.sync_or_create_store_instance(1, all_options_data)

        # 3.2. Check the rest of the google instances
        try:
            additional_google_channels = list(plugin_settings.get('instance', {}).get('google', {}).values())
        except AttributeError:
            additional_google_channels = []

        for channel in additional_google_channels:
            instance_id = channel.get('instance')
            if instance_id is not None and instance_id != '':
                self.sync_or_create_store_instance(instance_id, all_options_data)

    def sync_or_create_store_instance(self, instance_id: int, all_options_data: dict, instance_title=None):
        google_prefix = self.get_google_prefix(instance_id)
        google_store_data = safe_json(all_options_data.get(f'plugin_settings_{google_prefix}'))
        if not instance_title:
            google_store_name = google_store_data.get('sets', {}).get('page_shop_name', {}).get('value')
            instance_title = f'google:{google_store_name}' if google_store_name else f'Google-{instance_id}'

        try:
            store = GoogleStore.objects.get(store_instance_id=instance_id, user=self.user.models_user)
            store.sync(instance_title, all_options_data)
        except GoogleStore.DoesNotExist:
            # Create a new store to reflect the SureDone's data

            creds = google_store_data.get('creds', {})
            # system_token = google_store_data.get('creds', {}).get('system_token', {}).get('value')
            access_token = creds.get('access_token', {}).get('value')

            is_active = bool(access_token)

            GoogleStore.objects.create(
                sd_account=self.sd_account,
                store_instance_id=instance_id,
                user=self.user.models_user,
                title=instance_title,
                # commerce_manager_id=google_store_data.get('sets', {}).get('commerce_manager_id', {}).get('value'),
                is_active=is_active,
                creds=creds,
            )

    def product_save_draft(self, product_data: dict, store: GoogleStore, notes: str, activate: bool):
        """
        Save a new poduct to SureDone without publishing it to any Google store.
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
                                               store_type='google')

        # If the product was not successfully posted
        if not isinstance(sd_api_result, dict) or sd_api_result.get('api_response', {}).get('result') != 'success':
            return

        parent_guid = sd_api_result.get('parent_guid')

        # Fetch the product from SureDone and save the product if the product was successfully imported
        created_product = self.get_google_product_details(parent_guid, add_model_fields={'notes': notes})

        # If the SureDone returns no data, then the product did not get imported
        if not created_product or not isinstance(created_product, GoogleProduct):
            return

        # Init the default supplier
        store_info = product_data.get('store', {})
        original_url = product_data.get('original_url', '')
        supplier = GoogleSupplier.objects.create(
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

    def new_product_save(self, product_data: dict, store: GoogleStore, notes: str):
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
            store_type='google'
        )

        # If the product was not successfully posted
        if not isinstance(sd_api_result, dict) or sd_api_result.get('api_response', {}).get('result') != 'success':
            return

        parent_guid = sd_api_result.get('parent_guid')

        # Fetch the product from SureDone and save the product if the product was successfully imported
        created_product = self.get_google_product_details(parent_guid, add_model_fields={'notes': notes})

        # If the SureDone returns no data, then the product did not get imported
        if not created_product or not isinstance(created_product, GoogleProduct):
            return

        # Init the default supplier
        original_url = product_data.get('originalurl', '')
        supplier = GoogleSupplier.objects.create(
            store=store,
            product=created_product,
            product_guid=parent_guid,
            product_url=safe_str(original_url)[:512],
            is_default=True
        )
        created_product.set_default_supplier(supplier, commit=True)

        return sd_api_result

    def get_google_products(self, store_id: str, in_store: str, post_per_page=25, sort=None, board=None, product_board=None, request=None):
        """
        Get all Google products.

        :param product_board:
        :type product_board:
        :param store_id: Google store id
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
        user_stores = self.user.profile.get_google_stores(flat=True)
        res = GoogleProduct.objects.select_related('store') \
            .filter(user=self.user.models_user) \
            .filter(Q(store__in=user_stores) | Q(store=None))

        if store_id:
            if store_id == 'c':  # connected
                res = res.filter(status='active')
            elif store_id == 'n':  # non-connected
                res = res.exclude(status='active')

                in_store = safe_int(in_store)
                if in_store:
                    in_store = get_object_or_404(GoogleStore, id=in_store)
                    res = res.filter(store=in_store)

                    permissions.user_can_view(self.user, in_store)
            else:
                store = get_object_or_404(GoogleStore, id=store_id)
                res = res.filter(status='active', store=store)

                permissions.user_can_view(self.user, store)

        if product_board in ['added', 'not_added']:
            board_list = self.user.models_user.googleboard_set.all()
            if product_board == 'added':
                res = res.filter(GoogleBoard__in=board_list)
            elif product_board == 'not_added':
                res = res.exclude(GoogleBoard__in=board_list)

        if board:
            res = res.filter(GoogleBoard=board)
            permissions.user_can_view(self.user, get_object_or_404(GoogleBoard, id=board))

        if request:
            res = products_filter(res, request.GET)

        if sort:
            if re.match(r'^-?(title|price)$', sort):
                res = res.order_by(sort)
            elif re.match(r'^-?(date)$', sort):
                date_sort = re.sub(r'date', r'created_at', sort)
                res = res.order_by(date_sort)

        return res

    def convert_to_google_product_models(self, raw_products: list):
        """
        Convert a list of dictionaries into a list of GoogleProduct models

        :param raw_products: a list of dictionaries returned by SureDone API
        :type raw_products: list
        :return: a list of products converted into GoogleProduct models
        :rtype: list
        """
        products = []

        for product_data in raw_products:
            guid = product_data.get('guid')
            if not guid:
                continue
            # 1. If the object is already saved into the db:
            try:
                found_product = GoogleProduct.objects.get(guid=guid)

                # Compare the dates updated in SureDone
                date_updated_sd = self.parse_suredone_date(product_data.get('dateupdatedutc'))
                if not date_updated_sd:
                    date_updated_sd = self.parse_suredone_date(product_data.get('dateutc'))
                date_updated_db = arrow.get(found_product.sd_updated_at)

                # If the data in SureDone is newer, update the data in the db
                try:
                    if date_updated_sd > date_updated_db:
                        found_product = self.convert_to_google_product_model(product_data, product_to_update=found_product)
                        found_product.save()
                except TypeError:
                    found_product = self.convert_to_google_product_model(product_data, product_to_update=found_product)
                    found_product.save()

                products.append(found_product)

            # 2. If the object is not in the db yet:
            except GoogleProduct.DoesNotExist:
                # Create and save a new product
                product = self.convert_to_google_product_model(product_data)
                product.save()

                products.append(product)

        return products

    def convert_to_google_product_model(self, sd_product_data: dict, product_to_update: GoogleProduct = None,
                                        add_model_fields: dict = None):
        """
        Convert a SureDone product dictionary data into an GoogleProduct model params,
        then create or update a product

        :param sd_product_data: a dictionary with all SureDone product fields
        :type sd_product_data: dict
        :param product_to_update: a product to update if it's already created
            if not passed then a new product gets initialized and returned
        :type product_to_update: GoogleProduct
        :param add_model_fields: Additional fields to set on the Model
            where key is the field and value is the value to set it to
        :type add_model_fields: dict
        :return: an updated or created GoogleProduct model
        :rtype: GoogleProduct
        """
        if not add_model_fields:
            add_model_fields = {}

        guid = sd_product_data.get('guid')

        google_store_index = safe_int(sd_product_data.get('dropifiedconnectedstoreid'),
                                      default=sd_product_data.get('dropifiedconnectedstoreid'))
        if google_store_index is None or google_store_index == '':
            raise AttributeError(f'Connected store ID (dropifiedconnectedstoreid) is invalid for product with GUID {guid}')

        try:
            store = GoogleStore.objects.get(store_instance_id=google_store_index, user=self.user.models_user)
        except GoogleStore.DoesNotExist:
            store = None

        google_prefix = self.get_google_prefix(google_store_index)

        # Get product's google ID
        google_product_id = safe_int(sd_product_data.get(f'{google_prefix}productid'), 0)

        # Get google category ID
        google_category_id = safe_int(sd_product_data.get(f'{google_prefix}category'), None)

        # Get google product status ('active', 'pending' or '')
        product_status = sd_product_data.get(f'{google_prefix}status', '')

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
            'google_category_id': google_category_id,
            'google_store_index': google_store_index,
            'source_id': google_product_id,
            'variants_config': variants_config,
            'brand': sd_product_data.get('brand', ''),
            'page_link': sd_product_data.get('dropifiedgoogleproductlink', ''),
            'status': product_status,
            **add_model_fields
        }

        if product_to_update:
            for attr, value in model_params.items():
                setattr(product_to_update, attr, value)
            return product_to_update
        else:
            return GoogleProduct(**model_params)

    def get_google_product_details(self, parent_guid: str, add_model_fields: dict = None, smart_board_sync=False) -> GoogleProduct:
        """
        Get all product variants matching the passed GUID value as a SKU

        :param parent_guid: Parent variation product's GUID
        :type parent_guid: str
        :param add_model_fields: additional fields to set in the Model update or create step
        :type add_model_fields:
        :param smart_board_sync: Whether or not to perform a smart board sync when saving the product to the DB
        :type smart_board_sync: bool
        :return: a tuple with a list of GoogleProduct models and a list of variants
        :rtype: tuple(list[GoogleProduct], list)
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
                parent_product = GoogleProduct.objects.get(guid=parent_guid)
                parent_product = self.convert_to_google_product_model(sd_product_data, parent_product, add_model_fields)
            except GoogleProduct.DoesNotExist:
                parent_product = self.convert_to_google_product_model(sd_product_data, add_model_fields=add_model_fields)
            parent_product.save(smart_board_sync=smart_board_sync)

            google_prefix = self.get_google_prefix(parent_product.google_store_index)
            seen_variant_guids = [parent_guid]

            # Store the parent variant as the first variant
            self.update_or_create_product_variant(product_variant_data=sd_product_data, parent_product=parent_product,
                                                  google_prefix=google_prefix, variants_config=variants_config)
            # Extract relevant attributes/variants data
            for product_variant in attributes:
                seen_variant_guids.append(product_variant.get('guid'))
                self.update_or_create_product_variant(product_variant_data=product_variant, parent_product=parent_product,
                                                      google_prefix=google_prefix, variants_config=variants_config)

            # Find variants that were not returned by API and delete them
            removed_variants = GoogleProductVariant.objects.filter(sku=parent_guid).exclude(guid__in=seen_variant_guids)
            if removed_variants.count() > 0:
                removed_variants.delete()

            return parent_product
        else:
            return None

    def update_or_create_product_variant(self, product_variant_data: dict, parent_product: GoogleProduct,
                                         google_prefix: str, variants_config: list) -> GoogleProductVariant:
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
            'source_id': safe_int(product_variant_data.get(f'{google_prefix}productid')),
            'variant_data': json.dumps(extra_variant_params),
            'status': product_variant_data.get(f'{google_prefix}status', ''),
        }

        variant, created = GoogleProductVariant.objects.update_or_create(guid=guid, defaults=current_variant_params)
        return variant

    def get_google_prefix(self, store_index: int):
        """
        Compute google store prefix to use when getting corresponding SureDone product fields.
        Related SureDone Rules:
            1. All google-specific fields have a prefix "google"
            2. The first google store instance doesn't have any index next to "google"
            3. All the remainining google store instances have their corresponding index next to "google"

        :param store_index: google store instance index
        :type store_index: int
        :return: computed prefix for the requested google store instance
        :rtype: str
        """
        if store_index == 1:
            google_index_prefix = 'google'
        else:
            google_index_prefix = f'google{store_index}'
        return google_index_prefix

    def search_categories(self, search_term: str):
        """
        Search google categories by a product type keyword

        :param search_term: keyword to search for
        :type search_term: str
        :return: google categories matching the provided keyword
        :rtype:
        """
        return self.api.search_google_categories(search_term)

    def get_google_orders(self, store: GoogleStore, page=None, per_page=None, filters: dict = None):
        """
        Get all google orders.

        :param store: google store intance
        :type store: GoogleStore
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
        filters['platform_type'] = 'google'
        sd_orders, total_products_count = self.get_orders_by_platform_type(store, filters, page=page, per_page=per_page)

        normalized_orders = []
        orders_cache = {}
        if isinstance(sd_orders, list):
            for order in sd_orders:
                norm_item = GoogleOrderItem(self.user, store, order)

                for item in norm_item.items:
                    order_data_id = item.get('order_data_id')
                    order_data = item.get('order_data')
                    if order_data_id and order_data:
                        order_data = fix_order_data(self.user, order_data)
                        orders_cache[f'google_order_{order_data_id}'] = order_data

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
            tracked.order['id'] = tracked.order.get('oid')
            tracked.line = lines.get(f'{tracked.order_id}-{tracked.line_id}')

            if tracked.line:
                fulfillment_status = (self.get_item_fulfillment_status(tracked.order, tracked.line_id) or '').lower()
                tracked.line['fulfillment_status'] = fulfillment_status
                tracked.line['id'] = tracked.line_id
                tracked.line['product_id'] = tracked.line.get('itemdetails').get('product-id')

                if tracked.google_status != fulfillment_status:
                    tracked.google_status = fulfillment_status
                    tracked.save()

            new_tracker_orders.append(tracked)

        return new_tracker_orders

    def get_tracking_products(self, tracker_orders, per_page=50):
        ids = set([str(i.line_id) for i in tracker_orders])

        if not len(ids):
            return tracker_orders

        product_variants = GoogleProductVariant.objects.filter(guid__in=ids)
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

    def duplicate_product(self, product_data: dict, store: GoogleStore):
        """
        Save a new (duplicated) product to SureDone.
        :param product_data:
        :type product_data: dict
        :param store:
        :type store: GoogleStore
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
        created_product = self.get_google_product_details(parent_guid)

        # If the SureDone returns no data, then the product did not get imported
        if not created_product or not isinstance(created_product, GoogleProduct):
            return

        # Init the default supplier
        store_info = json.loads(product_data.get('store', {}))
        original_url = product_data.get('original_url', '')
        supplier = GoogleSupplier.objects.create(
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

    def disable_plugin_store(self, instance: int):
        return self.update_plugin_store_status('google', instance, 'off')

    def move_product_to_store(self, product: GoogleProduct, store: GoogleStore, skip_all_channels: bool = False):
        """
        Move Google product to passed Google store instance.
        :param product:
        :type product: GoogleProduct
        :param store:
        :type store: GoogleStore
        :param skip_all_channels:
        :type skip_all_channels: bool
        :return:
        :rtype:
        """
        updated_product = None
        try:
            sd_product_data = self.api.get_item_by_guid(product.guid)
            if sd_product_data and sd_product_data.get('guid'):
                variants = list(product.retrieve_variants())

                index_of_parent_variant = 0
                for i, variant in enumerate(variants):
                    if variant.parent_product and variant.parent_product.guid == variant.guid:
                        index_of_parent_variant = i
                    variants[i] = {
                        'guid': variant.guid,
                        'dropifiedconnectedstoreid': store.store_instance_id,
                    }

                updated_product_data = variants[index_of_parent_variant]
                updated_product_data['variants'] = variants
                self.update_product_details(updated_product_data, 'google', store.store_instance_id,
                                            skip_all_channels=skip_all_channels)

                updated_product = self.get_google_product_details(product.guid, smart_board_sync=True)
        except Exception:
            capture_exception()
        return updated_product


class GoogleOrderUpdater(SureDoneOrderUpdater):
    store_model = GoogleStore
    utils_class = GoogleUtils

    def delay_save(self, countdown=None):
        from google_core.tasks import order_save_changes

        order_save_changes.apply_async(
            args=[self.toJSON()],
            countdown=countdown
        )


class GoogleListPaginator(SimplePaginator):
    def page(self, number):
        number = self.validate_number(number)
        self.current_page = number
        params = {'page': number, 'per_page': self.per_page}

        # `self.object_list` is a `GoogleOrderListQuery` instance
        items = list(self.object_list.update_params(params).items())

        return self._get_page(items, number, self)


class GoogleOrderListQuery(object):
    def __init__(self, user, store, params=None):
        self._user = user
        self._store = store
        self._utils = GoogleUtils(self._user)

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
        self._items, self._total_count = self._utils.get_google_orders(self._store,
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


class GoogleOrderItem:
    def __init__(self, user, store: GoogleStore, sd_order_data: dict):
        self.user = user
        self.store = store
        self.suredone_data = sd_order_data
        google_utils = GoogleUtils(user)

        self.oid = sd_order_data.get('oid')
        self.id = self.oid

        all_items = sd_order_data.get('items', [])
        all_shipments = sd_order_data.get('shipments', [])
        product_ids = []
        for item in all_items:
            converted_google_id = safe_int(item.get('itemid'), default=None)
            if converted_google_id is not None:
                product_ids.append({'sku': item.get('sku'), 'google-id': converted_google_id})

        product_variants_by_guids = self.get_products_by_guids(product_ids)
        order_tracks_by_order_id = self.get_order_track_by_item([self.oid])

        self.connected_lines = len(product_variants_by_guids)
        self.placed_orders = 0
        self.lines_count = len(all_items)

        # Calculate google order ID, sales record number and order url link
        self.google_order_id = sd_order_data.get('ordernumber', '')
        if self.google_order_id:
            self.order_url = self.get_google_order_link(self.google_order_id)

        self.date = parse_suredone_date(sd_order_data.get('dateutc'))
        self.fulfillment_status = ''
        self.date_paid = parse_suredone_date(sd_order_data.get('paymentdate'))
        self.status = sd_order_data.get('status')
        self.partially_ordered = False
        self.tracked_lines = 0
        self.supplier_types = set()
        self.number = self.google_order_id
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
            google_product_id = safe_int(item.get('itemid'), default=None)
            product_variant = product_variants_by_guids.get(item.get('sku'))
            supplier = supplier_type = None
            is_pls = False
            item_id = item.get('sku')
            attributes = ''

            if product_variant:
                var_attributes_keys = self.get_attribute_keys_from_var_config(product_variant)
                var_attributes_keys = google_utils.convert_to_default_and_custom_fields(var_attributes_keys)
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
                'product_id': google_product_id,
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

        if self.tracked_lines != 0 and self.tracked_lines < self.lines_count and self.placed_orders < self.lines_count:
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

    def get_attribute_keys_from_var_config(self, product_variant: GoogleProductVariant) -> list:
        variants_config = product_variant.parent_product.variants_config_parsed
        var_attributes_keys = []
        if variants_config:
            var_attributes_keys = [i.get('title') for i in variants_config]
        return var_attributes_keys

    def get_order_data(self, item: dict, product: GoogleProductVariant, supplier: GoogleSupplier):
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
            'order_name': self.google_order_id,
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

    def get_order_data_variant(self, product_variant: GoogleProductVariant):
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
                'title': var_data.get(var_key) if var_data.get(var_key) else product_variant.variant_title,
                'image': product_variant.image,
                'sku': sku_values[i] if len(sku_values) > i else None
            })
        return variants

    def get_item_shipping_method(self, product_variant: GoogleProductVariant, item: dict, country_code: str):
        if item.get('supplier'):
            return product_variant.parent_product.get_shipping_for_variant(supplier_id=item['supplier'].id,
                                                                           variant_id=product_variant.guid,
                                                                           country_code=country_code)

    def get_order_ids(self, orders: list):
        return [safe_int(order.get('oid')) for order in orders]

    def get_products_by_source_ids(self, product_ids: list):
        product_by_source_id = {}
        store = self.store
        for product in GoogleProduct.objects.filter(store=store, source_id__in=product_ids):
            product_by_source_id[product.source_id] = product

        return product_by_source_id

    def get_products_by_guids(self, product_ids_data: list):
        products_by_guids = {}
        store = self.store

        for product_var_ids in product_ids_data:
            sku = product_var_ids.get('sku')

            try:
                product_var = GoogleProductVariant.objects.get(guid=sku, parent_product__store=store)
            except GoogleProductVariant.DoesNotExist:
                continue

            products_by_guids[product_var.guid] = product_var

        return products_by_guids

    def get_order_track_by_item(self, order_ids: list):
        track_by_item = {}
        store = self.store

        for track in GoogleOrderTrack.objects.filter(store=store, order_id__in=order_ids):
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

    def get_google_order_link(self, order_id: str):
        return f'{self.store.get_store_url()}/orders/{order_id}'

    def get_product_supplier(self, product):
        if product.has_supplier:
            return product.variant_specific_supplier

    def format_google_order_track_key(self, order_id: int, line_id: str, product_id: str):
        return f'{order_id}_{line_id}_{product_id}'


@add_to_class(UserProfile, 'sync_google_stores')
def user_sync_google_stores(self, use_cached=False):
    if self.user:
        GoogleUtils(self.user).sync_google_stores(use_cached=use_cached)


def get_store_from_request(request):
    store = None
    user = request.user
    stores = user.profile.get_google_stores()

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

        except (PermissionDenied, GoogleStore.DoesNotExist):
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

    for board in user.googleboard_set.all():
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
