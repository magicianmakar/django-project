import arrow
import itertools
import json
from celery import chain
from requests.exceptions import HTTPError

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db.models import ObjectDoesNotExist
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator

import suredone_core.tasks as sd_tasks
from alibaba_core.models import AlibabaOrderItem
from app.celery_base import celery_app
from fulfilment_fee.utils import process_sale_transaction_fee
from lib.exceptions import capture_exception, capture_message
from shopified_core import permissions
from shopified_core.api_base import ApiBase
from shopified_core.decorators import HasSubuserPermission
from shopified_core.utils import CancelledOrderAlert, clean_tracking_number, dict_val, get_domain, remove_link_query, safe_float, safe_int
from suredone_core.models import SureDoneAccount

from . import tasks
from .api_helper import EbayApiHelper
from .models import EbayBoard, EbayOrderTrack, EbayProduct, EbayProductVariant, EbayStore, EbaySupplier
from .utils import EbayOrderListQuery, EbayOrderUpdater, EbayUtils, get_ebay_store_specific_currency_options, get_fulfillment_meta


class EbayStoreApi(ApiBase):
    store_label = 'eBay'
    store_slug = 'ebay'
    product_model = EbayProduct
    store_model = EbayStore
    board_model = EbayBoard
    order_track_model = EbayOrderTrack
    helper = EbayApiHelper()

    def get_store_add(self, request, user, data):
        """
        Authorize a new ebay store. Steps to accomplish this:
            1. Make sure the user has a SureDone account, create a new one if not
            2. Find an instance ID to authorize. SD by default has one (instance ID = 1) ebay instance, all additional
               instances are in "plugin_settings". All additional instances need to be added manually. Created instances
               cannot be deleted but can get unauthorized. If there are existing unauthorized channels, those can be
               used for new authorization. Otherwise, a new instance needs to be created.
            3. Make sure the selected instance is enabled by checking if 'site_ebay{instance_id}connect' is 'on'
            4. Use the selected instance to authorize a new ebay channel and return the resulting authorization url
        :param request:
        :type request:
        :param user:
        :type user: User
        :param data:
        :type data: dict
        :return:
        :rtype:
        """
        if user.is_subuser:
            return self.api_error('Sub-Users can not add new stores.', status=401)

        can_add, total_allowed, user_count = permissions.can_add_store(user)

        if not can_add:
            if user.profile.plan.is_free and user.can_trial() and not user.profile.from_shopify_app_store():
                from shopify_oauth.views import subscribe_user_to_default_plan

                subscribe_user_to_default_plan(user)
            else:
                capture_message(
                    'Add Extra eBay Store',
                    level='warning',
                    extra={
                        'user': user.email,
                        'plan': user.profile.plan.title,
                        'stores': user.profile.get_ebay_stores().count()
                    }
                )

                if user.profile.plan.is_free and not user_count:
                    return self.api_error(f'Please Activate your account first by visiting:\n'
                                          f'{request.build_absolute_uri("/user/profile#plan")}', status=401)
                else:
                    return self.api_error('Your plan does not support connecting another eBay store. '
                                          'Please contact support@dropified.com to learn how to connect more stores.')

        pusher_channel = f'user_{user.id}'
        tasks_base_kwargs = {'pusher_channel': pusher_channel, 'user_id': user.id}
        sd_account = None

        # Verify the user has an SD account and if not create an account first
        try:
            sd_account = SureDoneAccount.objects.get(user=user.models_user, is_active=True)
        except SureDoneAccount.DoesNotExist:
            pass
        except SureDoneAccount.MultipleObjectsReturned:
            sd_account = SureDoneAccount.objects.filter(user=user.models_user, is_active=True).first()

        # If the user already has a SureDone account
        if sd_account is not None:
            tasks.add_new_ebay_store.apply_async(kwargs={
                **tasks_base_kwargs,
                'sd_account_id': sd_account.id,
            })
        # If the user doesn't have a SureDone account
        else:
            register_sd_account_task = sd_tasks.register_new_sd_user.s(**tasks_base_kwargs)
            add_ebay_store_task = tasks.add_new_ebay_store.s(**tasks_base_kwargs)
            configure_settings_task = sd_tasks.configure_user_custom_fields.s(user_id=user.id)
            chain(
                register_sd_account_task,
                add_ebay_store_task,
                configure_settings_task
            ).apply_async()

        pusher = {'key': settings.PUSHER_KEY, 'channel': pusher_channel}
        return self.api_success({'pusher': pusher})

    def get_reauthorize_store(self, request, user, data):
        """
        Reauthorize an existing ebay store. This is used when a token gets expired or a user revokes access.
        :param request:
        :type request:
        :param user:
        :type user: User
        :param data:
        :type data: dict
        :return:
        :rtype:
        """
        if user.is_subuser:
            return self.api_error('Sub-Users can not re-authorize stores.', status=401)

        store_id = request.GET.get('store')

        if not store_id:
            return self.api_error('Missing a required store parameter.')

        store = get_object_or_404(EbayStore, id=store_id)
        permissions.user_can_edit(user, store)

        pusher_channel = f'user_{user.id}'

        try:
            sd_account = SureDoneAccount.objects.get(user=user.models_user, is_active=True)
        except SureDoneAccount.DoesNotExist:
            return self.api_error('Invalid ebay configuration. Please contact Dropified support.')

        tasks.add_new_ebay_store.apply_async(kwargs={
            'user_id': user.id,
            'sd_account_id': sd_account.id,
            'pusher_channel': pusher_channel,
            'instance_id': store.store_instance_id,
            'event_name': 'ebay-reauthorize-store',
            'error_message': 'Failed to reauthorize the store. Please try again or contact support@dropified.com'
        })

        pusher = {'key': settings.PUSHER_KEY, 'channel': pusher_channel}
        return self.api_success({'pusher': pusher})

    def get_business_policies_sync(self, request, user, data):
        """
        Sync ebay business policies for the user's account.
        """
        store_id = request.GET.get('store')

        if not store_id:
            return self.api_error('Missing a required store parameter.')

        try:
            store = EbayStore.objects.get(id=store_id)
        except EbayStore.DoesNotExist:
            return self.api_error('Store not found.')

        permissions.user_can_view(user, store)
        pusher_channel = f'user_{user.id}'

        tasks.sync_advanced_options.apply_async(kwargs={
            'user_id': user.id,
            'store_id': store_id,
            'pusher_channel': pusher_channel,
        })

        pusher = {'key': settings.PUSHER_KEY, 'channel': pusher_channel}
        return self.api_success({'pusher': pusher})

    def get_advanced_settings(self, request, user, data):
        """
        Get ebay advanced settings contents. The settings include store's default shipping, return policies, etc.
        """
        store_id = request.GET.get('store')

        if not store_id:
            return self.api_error('Missing a required parameter: store.')

        try:
            store = EbayStore.objects.get(id=store_id)
        except EbayStore.DoesNotExist:
            return self.api_error('Store not found.')

        permissions.user_can_view(user, store)
        settings_data = EbayUtils(user).get_ebay_advanced_settings(store)

        try:
            if not settings_data.get('success'):
                return self.api_error(settings_data.get('message', ''))
        except AttributeError:
            return self.api_error('Something went wrong. Please try again.')

        return self.api_success(settings_data)

    def post_advanced_settings(self, request, user, data):
        """
        Update store's advanced settings. The settings include store's default shipping, return policies, etc.
        """
        data = data.dict()
        store_id = data.pop('store')

        if not store_id:
            return self.api_error('Missing a required store parameter.')

        store = get_object_or_404(EbayStore, id=store_id)
        permissions.user_can_edit(user, store)

        pusher_channel = f'user_{user.id}'
        ebay_prefix = EbayUtils(user).get_ebay_prefix(store.store_instance_id)
        request_data = {f"{ebay_prefix}_{k.replace('_', '')}": v for k, v in data.items()}

        tasks.update_profile_settings.apply_async(kwargs={
            'user_id': user.id,
            'store_id': store_id,
            'data': request_data,
            'pusher_channel': pusher_channel,
        })

        pusher = {'key': settings.PUSHER_KEY, 'channel': pusher_channel}
        return self.api_success({'pusher': pusher})

    def delete_store(self, request, user, data):
        """
        Revoke ebay authorization and delete the ebay store and all connected models.
        :param request:
        :type request:
        :param user:
        :type user:
        :param data:
        :type data:
        :return:
        :rtype:
        """
        if user.is_subuser:
            raise PermissionDenied()

        store_id = int(data.get('id', 0))
        if not store_id:
            return self.api_error('Store ID is required.', status=400)

        try:
            store = EbayStore.objects.get(pk=store_id)
        except EbayStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        permissions.user_can_delete(user, store)

        ebay_utils = EbayUtils(user)

        # Delete auth token on SureDone
        sd_api_request_data = {
            'instance': store.store_instance_id,
            'channel': 'ebay',
            'revoke': 'true',
        }
        sd_auth_channel_resp = ebay_utils.api.authorize_channel_v1(sd_api_request_data)

        # Handle SD API errors
        if not sd_auth_channel_resp or not isinstance(sd_auth_channel_resp, dict):
            return self.api_error('Something went wrong, please try again.', status=400)
        elif sd_auth_channel_resp.get('result') != 'success':
            error_message = sd_auth_channel_resp.get('message')
            error_message = error_message if error_message else 'Something went wrong. Please try again.'
            return self.api_error(error_message, status=400)

        # Disable the channel on SureDone
        channel_prefix = ebay_utils.get_ebay_prefix(store.store_instance_id)
        sd_disable_store_resp = ebay_utils.api.update_settings({f'site_{channel_prefix}connect': 'off'})

        # If failed to disable the ebay instance
        if sd_disable_store_resp.get('result') != 'success':
            return self.api_error('Failed to remove the eBay channel. Please try again'
                                  ' or contact support@dropified.com')

        store.is_active = False
        store.save()

        tasks.delete_all_store_products.apply_async(kwargs={
            'user_id': user.id,
            'store_id': store_id,
            'skip_all_channels': True,
        })

        return self.api_success()

    def get_store_verify(self, request, user, data):
        try:
            store = EbayStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except EbayStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        resp = None
        try:
            resp = EbayUtils(user).api.refresh_ebay_profiles(instance_id=store.filter_instance_id)
            resp.raise_for_status()

            return self.api_success({'store': store.get_store_url()})
        except HTTPError:
            try:
                resp_body = resp.json()
                error_message = resp_body.get('message')
                if 'Token does not match' in error_message:
                    error_message = 'Please reauthorize the store'
            except json.JSONDecodeError:
                error_message = None
            error = error_message if error_message else 'Unknown Issue'
            return self.api_error(f'API credentials are not correct\nError: {error}.')

    def get_search_categories(self, request, user, data):
        """
        Search eBay categories related to a keyword.
        For example, find all categories corresponding to the 'book' keyword

        :param request:
        :param user:
        :param data: API request parameters containing values for:
            search_term (str): A keyword for which to find eBay categories
            store_index (int): An index of the eBay store instance to use for the eBay API request
        :return: Categories found by the SureDone API
        :rtype: JsonResponse
        """
        search_term = data.get('search_term')
        store_index = data.get('store_index')
        if not search_term:
            self.api_error('Search term cannot be empty', status=404)
        return self.api_success({
            'data': EbayUtils(user).search_categories(store_index, search_term)
        })

    def get_category_specifics(self, request, user, data):
        """
        Get all required and recommended fields for an eBay category provided its ID

        :param request:
        :param user:
        :param data: API request params containing values for:
            ebay_category_id (int): eBay category ID, use get_search_categories API to get category IDs
            site_id (int): eBay site ID:
                https://developer.ebay.com/Devzone/merchandising/docs/concepts/siteidtoglobalid.html
        :return: Recommended and required fields for the provided category ID
        :rtype: JsonResponse
        """
        ebay_category_id = data.get('category_id')
        site_id = data.get('site_id')
        if site_id == '':
            site_id = 0

        if not ebay_category_id:
            self.api_error('eBay category ID cannot be empty', status=404)
        return self.api_success({
            'data': EbayUtils(user).get_category_specifics(site_id, ebay_category_id)
        })

    def post_product_export(self, request, user, data):
        """
        Publish a product to ebay

        :param request:
        :type request:
        :param user:
        :type user:
        :param data:
        :type data:
        :return:
        :rtype:
        """
        parent_guid = data.get('product')
        if not parent_guid:
            return self.api_error('Product ID cannot be empty.')

        store_id = data.get('store')
        if not store_id:
            return self.api_error('Store ID cannot be empty.')

        store = get_object_or_404(EbayStore, id=store_id)
        permissions.user_can_view(user, store)
        if not user.can('send_to_ebay.sub', store):
            raise PermissionDenied()

        if not user.can('send_to_store.use'):
            raise PermissionDenied()

        try:
            product = EbayProduct.objects.get(guid=parent_guid)
        except EbayProduct.DoesNotExist:
            return self.api_error('Product does not exist.')
        else:
            permissions.user_can_view(user, product)

        if product.source_id and product.store.id == store.id:
            return self.api_error('Product already connected to an eBay store.')

        tasks.product_export.apply_async(kwargs={
            'user_id': user.id,
            'parent_guid': parent_guid,
            'store_id': store_id
        }, countdown=0, expires=120)

        pusher = {'key': settings.PUSHER_KEY, 'channel': store.pusher_channel()}
        return self.api_success({'pusher': pusher})

    def post_product_update(self, request, user, data):
        """
        Update an existing product on SureDone and push updates to eBay

        :param request:
        :param user:
        :param data: API request params containing values for:
            product_data (dict): updated product data

        :return: SureDone's API response
        :rtype: JsonResponse
        """
        product_data = data.get('product_data')
        store_id = data.get('store')
        skip_publishing = data.get('skip_publishing')
        # variants_config = data.get('variants_config')

        if skip_publishing is not True:
            skip_publishing = False

        if not product_data:
            return self.api_error('Product data cannot be empty')

        if not store_id:
            return self.api_error('Store selection is invalid', status=404)

        if not isinstance(product_data, str) and not isinstance(product_data, dict):
            return self.api_error('Failed to parse product data.')

        if isinstance(product_data, str):
            try:
                product_data = json.loads(product_data)
            except (TypeError, json.JSONDecodeError):
                return self.api_error('Failed to parse product data.')

        parent_guid = product_data.get('guid')
        store = get_object_or_404(EbayStore, id=store_id)
        product = get_object_or_404(EbayProduct, guid=parent_guid)
        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)

        tasks.product_update.apply_async(kwargs={
            'user_id': user.id,
            'parent_guid': parent_guid,
            'product_data': product_data,
            'store_id': store_id,
            'skip_publishing': skip_publishing
        }, countdown=0, expires=120)
        pusher = {'key': settings.PUSHER_KEY, 'channel': store.pusher_channel()}
        return self.api_success({'pusher': pusher})

    def get_products_info(self, request, user, data):
        products = {}
        for guid in data.getlist('products[]'):
            try:
                product = EbayProduct.objects.get(guid=guid)
                permissions.user_can_view(user, product)

                products[guid] = json.loads(product.data)
            except EbayProduct.DoesNotExist:
                return self.api_error('Product not found.')

        return JsonResponse(products, safe=False)

    def delete_product(self, request, user, data):
        """
        Delete a single SureDone product by its GUID

        :param request:
        :param user:
        :param data: API request params:
            product (str): GUID of the product to delete
        :return: SureDone's API response
        :rtype: JsonResponse
        """
        parent_guid = data.get('product')
        try:
            product = EbayProduct.objects.get(guid=parent_guid)
        except EbayProduct.DoesNotExist:
            return self.api_error('Product not found.', status=404)
        permissions.user_can_delete(user, product)

        if not user.can('delete_products.sub', product.store):
            raise PermissionDenied()

        tasks.product_delete.apply_async(kwargs={
            'user_id': user.id,
            'parent_guid': parent_guid,
            'store_id': product.store.id,
        }, countdown=0, expires=120)

        pusher = {'key': settings.PUSHER_KEY, 'channel': product.store.pusher_channel()}
        return self.api_success({'pusher': pusher})

    def post_product_duplicate(self, request, user, data):
        """
        Duplicate all SureDone product by its SKU
        :param request:
        :param user:
        :param data: API request params:
            product (str): SKU of the product to duplicate
        :return: SureDone's API response
        :rtype: JsonResponse
        """
        parent_sku = data.get('product')

        try:
            product = EbayProduct.objects.get(guid=parent_sku)
        except EbayProduct.DoesNotExist:
            return self.api_error('Product not found.', status=404)

        product_data = json.loads(product.data)

        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)
        if not can_add:
            return self.api_error(
                f'Your current plan allows up to {total_allowed} saved product(s). Currently you '
                f'have {user_count} saved products.', status=401)

        tasks.product_duplicate.apply_async(kwargs={
            'user_id': user.id,
            'parent_sku': parent_sku,
            'product_data': product_data,
            'store_id': product.store.id,
        }, countdown=0, expires=120)

        pusher = {'key': settings.PUSHER_KEY, 'channel': product.store.pusher_channel()}
        return self.api_success({'pusher': pusher})

    def post_product_notes(self, request, user, data):
        guid = data.get('product')
        if not guid:
            return self.api_error('Product ID cannot be empty', status=400)

        product = get_object_or_404(EbayProduct, guid=guid)
        permissions.user_can_edit(user, product)

        product.notes = data.get('notes')
        product.save()

        return self.api_success()

    def post_supplier(self, request, user, data):
        original_link = remove_link_query(data.get('original-link'))
        if not original_link:
            return self.api_error('Original Link is not set', status=404)

        supplier_name = data.get('supplier-name')
        if not supplier_name:
            return self.api_error('Supplier Name is missing', status=422)

        supplier_url = remove_link_query(data.get('supplier-link', 'http://www.aliexpress.com/'))

        product_guid = data.get('product')

        if not product_guid:
            return self.api_error('Product ID is missing', status=422)

        supplier_id = data.get('export', None)

        try:
            product = EbayProduct.objects.get(guid=product_guid)
            permissions.user_can_edit(user, product)
            store = product.store

            if not store:
                return self.api_error('eBay store not found', status=500)
        except EbayProduct.DoesNotExist:
            product_title = data.get('product-title')
            product_image = data.get('product-image')
            product_price = data.get('product-price')
            product_attributes = data.get('product-attributes')
            store_id = data.get('ebay-store')

            try:
                store = EbayStore.objects.get(pk=store_id)
                permissions.user_can_view(user, store)
            except EbayStore.DoesNotExist:
                return self.api_error('Store not found', status=404)

            can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)
            if not can_add:
                return self.api_error(f'Your current plan allows up to {total_allowed} saved product(s).'
                                      f' Currently you have {user_count} saved products.', status=401)

            # Create the product from orders' data
            product_data = {
                'guid': product_guid,
                'title': product_title,
                'price': product_price,
                'media1': product_image,
                'varianttitle': product_attributes,
                'store': store,
                'originalurl': original_link,
            }
            notes = ''
            ebay_utils = EbayUtils(user)
            resp = ebay_utils.new_product_save(product_data, store, notes)

            if not isinstance(resp, dict) or resp.get('api_response', {}).get('1', {}).get('result') != 'success':
                capture_message(
                    'Error connecting an eBay supplier.',
                    extra={
                        'guid': product_guid,
                        'sd_api_response': resp,
                        'user_id': user.id,
                        'store_id': store.id,
                    }
                )
                return self.api_error('Failed to connect the product. Please try again later.', status=400)

            product = EbayProduct.objects.get(guid=product_guid)
            supplier_id = product.default_supplier_id

        if get_domain(original_link) == 'dropified':
            try:
                # TODO: handle dropified suppliers
                pass
            except:
                capture_exception(level='warning')
                return self.api_error('Product supplier is not correct', status=500)

        elif 'click.aliexpress.com' in original_link.lower():
            return self.api_error('The submitted Aliexpress link will not work properly with order fulfillment')

        reload = False
        try:
            product_supplier = EbaySupplier.objects.get(id=supplier_id, store__in=user.profile.get_ebay_stores())

            product_supplier.product = product
            product_supplier.product_url = original_link
            product_supplier.supplier_name = supplier_name
            product_supplier.supplier_url = supplier_url
            product_supplier.save()

        except (ValueError, EbaySupplier.DoesNotExist):
            reload = True
            is_default = not product.have_supplier()

            product_supplier = EbaySupplier.objects.create(
                store=store,
                product=product,
                product_guid=product_guid,
                product_url=original_link,
                supplier_name=supplier_name,
                supplier_url=supplier_url,
                is_default=is_default
            )

            supplier_id = product_supplier.id

        if not product.have_supplier() or not supplier_id:
            reload = True
            product.set_default_supplier(product_supplier, commit=True)

        return self.api_success({'reload': reload})

    def post_supplier_default(self, request, user, data):
        product_guid = data.get('product')
        supplier_id = data.get('export')

        if not product_guid or not supplier_id:
            return self.api_error('Product ID and Supplier ID are required fields.')

        product = get_object_or_404(EbayProduct, guid=product_guid)
        permissions.user_can_edit(user, product)

        try:
            supplier = EbaySupplier.objects.get(id=supplier_id, product=product)
        except EbaySupplier.DoesNotExist:
            return self.api_error('Supplier not found.\nPlease reload the page and try again.')

        product.set_default_supplier(supplier, commit=True)

        return self.api_success()

    def delete_supplier(self, request, user, data):
        product_guid = data.get('product')
        supplier_id = data.get('supplier')

        product = get_object_or_404(EbayProduct, guid=product_guid)
        permissions.user_can_edit(user, product)

        try:
            supplier = EbaySupplier.objects.get(id=supplier_id, product=product)
        except EbaySupplier.DoesNotExist:
            return self.api_error('Supplier not found.\nPlease reload the page and try again.')

        need_update = product.default_supplier == supplier

        supplier.delete()

        if need_update:
            other_supplier = product.get_suppliers().first()
            if other_supplier:
                product.set_default_supplier(other_supplier)
                product.save()

        return self.api_success()

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def post_board_add_products(self, request, user, data):
        try:
            board = EbayBoard.objects.get(id=data.get('board'))
            permissions.user_can_edit(user, board)

        except EbayBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)

        product_ids = data.getlist('products[]')
        products = EbayProduct.objects.filter(guid__in=product_ids)

        for product in products:
            permissions.user_can_edit(user, product)

        board.products.add(*products)

        return self.api_success()

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def post_product_board(self, request, user, data):
        try:
            product = EbayProduct.objects.get(guid=data.get('product'))
            permissions.user_can_edit(user, product)
        except EbayProduct.DoesNotExist:
            return self.api_error('Product not found.', status=404)

        if data.get('board') == '0':
            product.boards.clear()
            product.save()
            return self.api_success()
        else:
            try:
                board = EbayBoard.objects.get(id=data.get('board'))
                permissions.user_can_edit(user, board)
                board.products.add(product)
                board.save()
                return self.api_success({'board': {'id': board.id, 'title': board.title}})
            except EbayBoard.DoesNotExist:
                return self.api_error('Board not found.', status=404)

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def delete_board_products(self, request, user, data):
        try:
            pk = safe_int(dict_val(data, ['board', 'board_id']))
            board = EbayBoard.objects.get(pk=pk)
            permissions.user_can_edit(user, board)

        except EbayBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)

        product_ids = data.getlist('products[]')
        products = EbayProduct.objects.filter(guid__in=product_ids)
        for product in products:
            permissions.user_can_edit(user, product)
            board.products.remove(product)

        return self.api_success()

    def delete_board(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        try:
            pk = safe_int(data.get('board_id'))
            board = EbayBoard.objects.get(pk=pk)
        except EbayBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)
        else:
            permissions.user_can_delete(user, board)
            board.delete()
            return self.api_success()

    def get_order_notes(self, request, user, data):
        store = EbayStore.objects.get(id=data['store'])
        permissions.user_can_view(user, store)
        order_ids = data.get('order_ids').split(',')

        tasks.get_latest_order_note_task.apply_async(args=[user.id, store.id, order_ids], expires=120)

        return self.api_success()

    def post_fulfill_order(self, request, user, data):
        store_id = data.get('fulfill-store')
        if not store_id:
            capture_exception(level='error', extra={'message': 'Store ID not provided to fulfull order'})
            return self.api_error('Store is required.', status=404)

        try:
            store = EbayStore.objects.get(id=store_id)
        except EbayStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        if not user.can('place_orders.sub', store):
            raise PermissionDenied()

        permissions.user_can_view(user, store)

        tracking_number = data.get('fulfill-tracking-number', '')
        provider_id = safe_int(data.get('fulfill-provider', 0))
        order_id = safe_int(data['fulfill-order-id'])
        line_id = data['fulfill-line-id']
        date_shipped = data.get('fulfill-date-shipped')

        try:
            date_shipped = arrow.get(date_shipped, 'MM/DD/YYYY').isoformat()
        except:
            pass

        ebay_utils = EbayUtils(user)
        provider_name = ebay_utils.get_shipping_carrier_name(provider_id)

        if provider_name == 'Custom Provider':
            provider_name = data.get('fulfill-provider-name', provider_name)
        if not provider_name:
            return self.api_error('Invalid shipping provider')

        ship_meta_data = get_fulfillment_meta(
            shipping_carrier_name=provider_name,
            tracking_number=tracking_number,
            item_sku=line_id,
            date_shipped=date_shipped
        )

        api_request_data = {
            'shipments': [ship_meta_data],
            'shippingstatus': 'COMPLETE',
        }

        r = None
        api_results = None
        try:
            r = ebay_utils.api.update_order_details(order_id, api_request_data)
            api_results = r.json().get('results')
            r.raise_for_status()
        except:
            capture_exception(level='warning', extra={'response': r.text if r else ''})
            message = 'eBay API Error. Please try again.'
            if isinstance(api_results, dict):
                failed_results = [x.get('message') for x in api_results.get('failed', {}) if 'message' in x]
                message = '\n '.join(failed_results) or message
            return self.api_error(message)

        if not isinstance(api_results, dict) or api_results.get('failed'):
            failed_results = [x.get('message') for x in api_results.get('failed', {}) if 'message' in x]
            message = '\n '.join(failed_results) or 'Something went wrong. Please try again'
            return self.api_error(message)

        # if len(utils.get_unfulfilled_items(r.json())) == 0:
        #     utils.update_order_status(store, order_id, 'completed')

        return self.api_success()

    def post_order_fulfill(self, request, user, data):
        store_id = data.get('store')
        order_id = safe_int(data.get('order_id'))
        item_sku = data.get('line_id').split(',') if data.get('line_id') else []
        source_id = data.get('aliexpress_order_id')

        if not order_id or not store_id:
            return self.api_error('Required input is missing')

        try:
            assert len(source_id) > 0, 'Empty Order ID'
            source_id.encode('ascii')
        except AssertionError as e:
            capture_message('Invalid supplier order ID')
            return self.api_error(str(e), status=501)
        except UnicodeEncodeError:
            return self.api_error('Order ID is invalid', status=501)

        try:
            store = EbayStore.objects.get(id=safe_int(store_id))
        except EbayStore.DoesNotExist:
            capture_exception()
            return self.api_error(f'Store {store_id} not found', status=404)

        if not user.can('place_orders.sub', store):
            raise PermissionDenied()

        permissions.user_can_view(user, store)

        if not item_sku:
            filters = {
                'oid': order_id
            }
            order = EbayOrderListQuery(user, store, params=filters).items()[0]
            for item in order.items:
                if EbayProductVariant.objects.filter(guid=item.get('id')):
                    item_sku.append(item.get('id'))

        order_updater = EbayOrderUpdater(user, store, order_id)

        for line_id in item_sku:
            tracks = EbayOrderTrack.objects.filter(store=store,
                                                   order_id=order_id,
                                                   line_id=line_id)
            tracks_count = tracks.count()

            if tracks_count > 1:
                tracks.delete()

            if tracks_count == 1:
                saved_track = tracks.first()

                if saved_track.source_id and source_id != saved_track.source_id:
                    return self.api_error('This order already has a supplier order ID', status=422)

            seen_source_orders = EbayOrderTrack.objects.filter(store=store, source_id=source_id)
            seen_source_orders = seen_source_orders.values_list('order_id', flat=True)

            if len(seen_source_orders) and int(order_id) not in seen_source_orders and not data.get('forced'):
                return self.api_error('Supplier order ID is linked to another order', status=409)

            track, created = EbayOrderTrack.objects.update_or_create(
                store=store,
                order_id=order_id,
                line_id=line_id,
                defaults={
                    'user': user.models_user,
                    'source_id': source_id,
                    'source_type': data.get('source_type'),
                    'created_at': timezone.now(),
                    'updated_at': timezone.now(),
                    'status_updated_at': timezone.now()})

            if user.profile.get_config_value('aliexpress_as_notes', True):
                order_updater.mark_as_ordered_note(line_id, source_id, track)

            store.pusher_trigger('order-source-id-add', {
                'track': track.id,
                'order_id': order_id,
                'line_id': line_id,
                'source_id': source_id,
                'source_url': track.get_source_url(),
            })

            order_updater.update_order_status('ORDERED')

        if not settings.DEBUG and 'oberlo.com' not in request.META.get('HTTP_REFERER', ''):
            order_updater.delay_save()

        return self.api_success({'order_track_id': track.id})

    def post_order_fulfill_update(self, request, user, data):
        if data.get('store'):
            store = EbayStore.objects.get(pk=safe_int(data['store']))
            if not user.can('place_orders.sub', store):
                raise PermissionDenied()

        try:
            order = EbayOrderTrack.objects.get(id=data.get('order'))
            permissions.user_can_edit(user, order)
        except EbayOrderTrack.DoesNotExist:
            return self.api_error('Order Not Found', status=404)

        cancelled_order_alert = CancelledOrderAlert(user.models_user,
                                                    data.get('source_id'),
                                                    data.get('end_reason'),
                                                    order.source_status_details,
                                                    order)

        order.source_status = data.get('status')
        order.source_tracking = clean_tracking_number(data.get('tracking_number'))
        order.status_updated_at = timezone.now()

        try:
            order_data = json.loads(order.data)
            if 'aliexpress' not in order_data:
                order_data['aliexpress'] = {}
        except:
            order_data = {'aliexpress': {}}

        order_data['aliexpress']['end_reason'] = data.get('end_reason')

        try:
            order_data['aliexpress']['order_details'] = json.loads(data.get('order_details'))
        except:
            pass

        order.data = json.dumps(order_data)

        order.save()

        # Send e-mail notifications for cancelled orders
        cancelled_order_alert.send_email()

        # process fulfilment fee
        process_sale_transaction_fee(order)

        return self.api_success()

    def delete_order_fulfill(self, request, user, data):
        order_id, line_id = safe_int(data.get('order_id')), data.get('line_id')
        orders = EbayOrderTrack.objects.filter(user=user.models_user,
                                               order_id=order_id,
                                               line_id=line_id)
        deleted_ids = []

        if not len(orders) > 0:
            return self.api_error('Order not found.', status=404)

        for order in orders:
            permissions.user_can_delete(user, order)
            deleted_ids.append(order.id)
            order.delete()
            data = {
                'store_id': order.store.id,
                'order_id': order.order_id,
                'line_id': order.line_id,
                'product_id': getattr(order, 'product_id', None)
            }

            order.store.pusher_trigger('order-source-id-delete', data)

        AlibabaOrderItem.objects.filter(order_track_id__in=deleted_ids).delete()

        return self.api_success()

    def post_order_note(self, request, user, data):
        try:
            store = EbayStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        order_id = data['order_id']
        note = data['note']

        if note is None:
            return self.api_error('Note required')

        latest_note = EbayUtils(user).get_latest_order_note(order_id)
        if latest_note == note:
            return self.api_success()
        else:
            try:
                resp = EbayOrderUpdater(user, store, order_id).add_ebay_order_note(order_id, note)
                if resp.get('results', {}).get('successful'):
                    return self.api_success()
                else:
                    return self.api_error(f'{self.store_label} API Error', status=422)
            except HTTPError:
                return self.api_error(f'{self.store_label} API Error', status=422)

    def post_variant_image(self, request, user, data):
        skip_publishing = data.get('skip_publishing', True)
        parent_guid = data.get('parent_guid')

        try:
            store = EbayStore.objects.get(id=data.get('store'))
        except EbayStore.DoesNotExist:
            return self.api_error('Store not found', status=404)
        try:
            product = EbayProduct.objects.get(guid=parent_guid)
        except EbayProduct.DoesNotExist:
            return self.api_error('Product not found', status=404)

        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)

        product_data = {
            'guid': data.get('variant_guid'),
            'media1': data.get('image_src')
        }

        tasks.product_update.apply_async(kwargs={
            'user_id': user.id,
            'parent_guid': parent_guid,
            'product_data': product_data,
            'store_id': store.id,
            'skip_publishing': skip_publishing
        }, countdown=0, expires=120)

        pusher = {'key': settings.PUSHER_KEY, 'channel': store.pusher_channel()}
        return self.api_success({'pusher': pusher})

    def get_currency(self, request, user, data):
        currencies = get_ebay_store_specific_currency_options()

        try:
            store = self.store_model.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)
            store_currency = store.currency_format.replace('{{ amount }}', '') if store.currency_format else '$'

        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        return self.api_success({
            'currency': store.currency_format or '',
            'store': store.id,
            'currencies': currencies,
            'store_currency': store_currency,
        })

    def post_currency(self, request, user, data):
        currencies = get_ebay_store_specific_currency_options()
        try:
            store = self.store_model.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        if not user.can('edit_settings.sub'):
            raise PermissionDenied()

        # Update the ebay store settings in Dropified DB
        if data.get('currency'):
            for currency in currencies:
                if currency[0] == data.get('currency'):
                    store.currency_format = f'{currency[2]}{{{{ amount }}}}'
                    break
        else:
            store.currency_format = ''
        store.save()

        # Update the ebay store settings in SureDone
        ebay_utils = EbayUtils(user)
        ebay_prefix = ebay_utils.get_ebay_prefix(store.store_instance_id)
        ebay_settings_config = {f'{ebay_prefix}_currency': data.get('currency', '')}

        result = ebay_utils.update_user_business_settings(ebay_settings_config)

        if result.get('error'):
            return self.api_error(f'Failed to update eBay currency settings. {result.get("error_message", "")}')

        return self.api_success()

    def post_products_supplier_sync(self, request, user, data):
        try:
            store = EbayStore.objects.get(id=data.get('store'))
            permissions.user_can_edit(user, store)
        except EbayStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        products = [product for product in data.get('products').split(',') if product]
        if not products:
            return self.api_error('No selected products to sync', status=422)

        user_store_supplier_sync_key = 'user_store_supplier_sync_{}_{}'.format(user.id, store.id)
        if cache.get(user_store_supplier_sync_key) is not None:
            cache.delete(user_store_supplier_sync_key)
            return self.api_error('Sync in progress', status=404)
        sync_price = data.get('sync_price', False)
        price_markup = safe_float(data['price_markup'])
        compare_markup = safe_float(data['compare_markup'])
        sync_inventory = data.get('sync_inventory', False)
        task = tasks.products_supplier_sync.apply_async(
            args=[store.id, user.id, products, sync_price, price_markup, compare_markup, sync_inventory, user_store_supplier_sync_key], expires=180)
        cache.set(user_store_supplier_sync_key, task.id, timeout=3600)
        return self.api_success({'task': task.id})

    def post_products_supplier_sync_stop(self, request, user, data):
        try:
            store = EbayStore.objects.get(id=data.get('store'))
            permissions.user_can_edit(user, store)
        except EbayStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        user_store_supplier_sync_key = 'user_store_supplier_sync_{}_{}'.format(user.id, store.id)
        task_id = cache.get(user_store_supplier_sync_key)
        if task_id is not None:
            celery_app.control.revoke(task_id, terminate=True)
            cache.delete(user_store_supplier_sync_key)
            return self.api_success()
        return self.api_error('No Sync in progress', status=404)

    def get_import_product_options(self, request, user, data):
        # TODO: add filters to imports
        try:
            store = EbayStore.objects.get(id=data.get('store'))
            permissions.user_can_edit(user, store)
        except EbayStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        page_limit = safe_int(data.get('ppp'), 10)
        if page_limit < 1:
            page_limit = 10

        page = safe_int(data.get('current_page'), 1)
        if page < 1:
            page = 1

        task = tasks.get_import_product_options.apply_async(kwargs={
            'store_id': store.id,
            'user_id': user.id,
            'page_limit': page_limit,
            'page': page,
        })

        return self.api_success({'task': task.id})

    def get_import_products_status(self, request, user, data):
        try:
            store = EbayStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)
        except EbayStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        try:
            result = EbayUtils(user).get_import_products_status(store=store)
            return self.api_success({'data': result})
        except:
            return self.api_error('Something went wrong. Please try again later.')

    def post_new_products_import_job(self, request, user, data):
        try:
            store = EbayStore.objects.get(id=data.get('store'))
            permissions.user_can_edit(user, store)
        except EbayStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        try:
            result = EbayUtils(user).start_new_products_import_job(store=store)
        except:
            return self.api_error('Something went wrong. Please try again later.')

        if result.get('result') == 'success':
            return self.api_success({'data': result})
        else:
            return self.api_error('Something went wrong. Please try again later.')

    def post_import_product(self, request, user, data):
        store_id = data.get('store')
        supplier = data.get('supplier')
        vendor_name = data.get('vendor_name')
        vendor_url = data.get('vendor_url', 'http://www.aliexpress.com/')
        product_guid = data.get('product')
        product_variants_count = safe_int(data.get('variants_count'), None)
        csv_position = safe_int(data.get('csv_index_position'), None)

        if any(x is None or x == '' for x in [store_id, supplier, vendor_name, vendor_url, product_guid, csv_position, product_variants_count]):
            return self.api_error('Missing or invalid required parameters.')

        try:
            store = EbayStore.objects.get(id=store_id)
            permissions.user_can_edit(user, store)
        except EbayStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        # Check if a user has reached products limit
        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)

        if not can_add:
            return self.api_error("Woohoo! 🎉. You are growing and you've hit your account limit for products. "
                                  'Upgrade your plan to keep importing new products')

        task = tasks.import_product.apply_async(kwargs={
            'store_id': store_id,
            'user_id': user.id,
            'supplier_url': supplier,
            'vendor_name': vendor_name,
            'vendor_url': vendor_url,
            'product_guid': product_guid,
            'csv_position': csv_position,
            'product_variants_count': product_variants_count,
        })

        return self.api_success({'task': task.id})

    def post_update_product_with_import(self, request, user, data):
        """
        Sync an existing product with the imported ebay data
        """
        product_guid = data.get('product')
        product_variants_count = safe_int(data.get('variants_count'), None)
        csv_position = safe_int(data.get('csv_index_position'), None)

        if any(x is None or x == '' for x in [product_guid, csv_position, product_variants_count]):
            return self.api_error('Missing or invalid required parameters.')

        try:
            product = EbayProduct.objects.get(guid=product_guid)
            permissions.user_can_edit(user, product)
        except EbayStore.DoesNotExist:
            return self.api_error('Product not found', status=404)

        task = tasks.sync_product_with_import_file.apply_async(kwargs={
            'store_id': product.store.id,
            'user_id': user.id,
            'product_id': product.id,
            'csv_position': csv_position,
            'product_variants_count': product_variants_count,
        })

        return self.api_success({'task': task.id})

    def delete_disconnect_product(self, request, user, data):
        store_id = data.get('store')
        product_guid = data.get('product')

        try:
            product = EbayProduct.objects.get(guid=product_guid, user=user.models_user)
            permissions.user_can_delete(user, product)
        except EbayProduct.DoesNotExist:
            return self.api_error('Product not found', status=404)

        tasks.product_delete.apply_async(kwargs={
            'user_id': user.id,
            'parent_guid': product_guid,
            'store_id': store_id,
            'skip_all_channels': True,
        })

        return self.api_success()

    def post_bundles_mapping(self, request, user, data):
        if not user.can('mapping_bundle.use'):
            return self.api_error('Your current plan doesn\'t have this feature.', status=403)

        product = EbayProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        product.set_bundle_mapping(data.get('mapping'))
        product.save()

        return self.api_success()

    def post_ebay_products(self, request, user, data):
        store = safe_int(data.get('store'))
        query = data.get('query')
        if not store:
            return self.api_error('No store was selected', status=404)
        try:
            store = EbayStore.objects.get(id=store)
            permissions.user_can_view(user, store)
            products = tasks.get_import_product_options(store.id, user.id, page=1, page_limit=100)
            if not products:
                return self.api_error('No products found', status=404)

            products = products.get('products', [])

            for product in products:
                product['image'] = {'src': product.get('image')}
                product['name'] = product.pop('title', 'Product')
                product['connected'] = product.get('status') == 'connected'
                product['id'] = product.pop('product_id', 0)

            if data.get('hide_connected'):
                products = [p for p in products if not p.get('connected')]

            return self.api_success({'products': products, 'query': query, 'store': store.id})

        except EbayStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

    def post_product_connect(self, request, user, data):
        try:
            product = EbayProduct.objects.get(id=data.get('product'))
        except EbayProduct.DoesNotExist:
            return self.api_error('Product not found', status=404)
        permissions.user_can_edit(user, product)

        try:
            store = EbayStore.objects.get(id=data.get('store'))
        except EbayStore.DoesNotExist:
            return self.api_error('Store not found', status=404)
        permissions.user_can_view(user, store)

        ebay_relist_id = data.get('ebay_relist_id')
        if not ebay_relist_id:
            return self.api_error('No ebay relist id was provided', status=400)

        source_id = safe_int(data.get('ebay'))
        if source_id != product.source_id or product.store != store:
            connected_to = self.helper.get_connected_products(self.product_model, store, source_id)

            if connected_to.exists():
                error_message = ['The selected product is already connected to:\n']
                connected_products = connected_to.values_list('store', 'guid')
                links = []

                for store_id, guid in connected_products:
                    path = self.helper.get_product_path({'store_id': store_id, 'guid': guid})
                    links.append(request.build_absolute_uri(path))

                error_message = itertools.chain(error_message, links)
                error_message = '\n'.join(error_message)

                return self.api_error(error_message, status=500)

            # Make the change on SureDone
            task = tasks.connect_product_to_ebay.apply_async(kwargs={
                'user_id': user.id,
                'store_id': store.id,
                'product_id': product.id,
                'source_id': source_id,
                'ebay_relist_id': ebay_relist_id,
            })
            return self.api_success({'task': task.id})

        return self.api_error('Product already connected')

    def delete_product_connect(self, request, user, data):
        product_ids = data.get('product').split(',')
        products = EbayProduct.objects.filter(id__in=product_ids)

        for product in products:
            permissions.user_can_edit(user, product)

            source_id = product.source_id
            if source_id:
                # Make the change on SureDone
                task = tasks.disconnect_product_from_ebay.apply_async(kwargs={
                    'user_id': user.id,
                    'store_id': product.store.id,
                    'product_id': product.id,
                })
                return self.api_success({'task': task.id})

        return self.api_error('No products found', status=404)

    def get_autocomplete_variants(self, request, user, data):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'User login required'})

        q = request.GET.get('query', '').strip()
        if not q:
            q = request.GET.get('term', '').strip()

        if not q:
            return JsonResponse({'query': q, 'suggestions': []}, safe=False)

        try:
            store = EbayStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

            ebay_product = EbayProduct.objects.get(id=data.get('product'))
            permissions.user_can_edit(user, ebay_product)
            ebay_product_variants = list(ebay_product.retrieve_variants())

            results = []
            for variant in ebay_product_variants:
                results.append({
                    'value': variant.variant_title,
                    'data': variant.id,
                    'image': variant.image
                })

            return JsonResponse({'query': q, 'suggestions': results}, safe=False)

        except EbayStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

        except EbayProduct.DoesNotExist:
            return JsonResponse({'error': 'Product not found'}, status=404)
