import arrow
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
from suredone_core.utils import SureDonePusher

from . import tasks
from .api_helper import GoogleApiHelper
from .models import GoogleBoard, GoogleOrderTrack, GoogleProduct, GoogleProductVariant, GoogleStore, GoogleSupplier
from .utils import GoogleOrderListQuery, GoogleOrderUpdater, GoogleUtils, get_fulfillment_meta


class GoogleStoreApi(ApiBase):
    store_label = 'Google'
    store_slug = 'google'
    product_model = GoogleProduct
    store_model = GoogleStore
    board_model = GoogleBoard
    order_track_model = GoogleOrderTrack
    helper = GoogleApiHelper()

    def get_store_add(self, request, user, data):
        """
        Authorize a new google store. Steps to accomplish this:
            1. Make sure the user has a SureDone account, create a new one if not
            2. Find an instance ID to authorize. SD by default has one (instance ID = 1) google instance, all additional
               instances are in "plugin_settings". All additional instances need to be added manually. Created instances
               cannot be deleted but can get unauthorized. If there are existing unauthorized channels, those can be
               used for new authorization. Otherwise, a new instance needs to be created.
            3. Make sure the selected instance is enabled by checking if 'site_google{instance_id}connect' is 'on'
            4. Use the selected instance to authorize a new google channel and return the resulting authorization url
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
                    'Add Extra Google Store',
                    level='warning',
                    extra={
                        'user': user.email,
                        'plan': user.profile.plan.title,
                        'stores': user.profile.get_google_stores().count()
                    }
                )

                if user.profile.plan.is_free and not user_count:
                    return self.api_error(f'Please Activate your account first by visiting:\n'
                                          f'{request.build_absolute_uri("/user/profile#plan")}', status=401)
                else:
                    return self.api_error('Your plan does not support connecting another Google store. '
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
            tasks.add_new_google_store.apply_async(kwargs={
                **tasks_base_kwargs,
                'sd_account_id': sd_account.id,
            })
        # If the user doesn't have a SureDone account
        else:
            register_sd_account_task = sd_tasks.register_new_sd_user.s(**tasks_base_kwargs)
            add_google_store_task = tasks.add_new_google_store.s(**tasks_base_kwargs)
            configure_settings_task = sd_tasks.configure_user_custom_fields.s(user_id=user.id)
            chain(
                register_sd_account_task,
                add_google_store_task,
                configure_settings_task
            ).apply_async()

        pusher = {'key': settings.PUSHER_KEY, 'channel': pusher_channel}
        return self.api_success({'pusher': pusher})

    def get_reauthorize_store(self, request, user, data):
        """
        Reauthorize an existing google store. This is used when a token gets expired or a user revokes access.
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

        store = get_object_or_404(GoogleStore, id=store_id)
        permissions.user_can_edit(user, store)

        pusher_channel = f'user_{user.id}'

        try:
            sd_account = SureDoneAccount.objects.get(user=user.models_user, is_active=True)
        except SureDoneAccount.DoesNotExist:
            return self.api_error('Invalid Google configuration. Please contact Dropified support.')

        tasks.add_new_google_store.apply_async(kwargs={
            'user_id': user.id,
            'sd_account_id': sd_account.id,
            'pusher_channel': pusher_channel,
            'instance_id': store.store_instance_id,
            'event_name': 'google-reauthorize-store',
            'error_message': 'Failed to reauthorize the store. Please try again or contact support@dropified.com'
        })

        pusher = {'key': settings.PUSHER_KEY, 'channel': pusher_channel}
        return self.api_success({'pusher': pusher})

    def post_onboard_store(self, request, user, data):
        data = data.dict()
        store_id = data.get('store_id')
        cms_id = data.get('cms_id')

        if not store_id:
            return self.api_error('Missing a required "store_id" field.')
        if not cms_id:
            return self.api_error('Missing a required "cms_id" field.')

        store = get_object_or_404(GoogleStore, id=store_id)
        permissions.user_can_edit(user, store)

        result = None
        try:
            result = GoogleUtils(user).onboard_google_instance(cms_id=cms_id, instance_id=store.filter_instance_id)
            if result.get('failed'):
                capture_message(extra={
                    'message': 'Errors when onboarding a Google store',
                    'store_id': store.id,
                    'user_id': user.id,
                    'sd_response': result,
                })
        except HTTPError:
            capture_exception(extra={
                'message': 'Failed to onboard a Google store',
                'store_id': store.id,
                'user_id': user.id,
                'sd_response': result,
            })
            return self.api_error('Error onboarding the Google store. Please try again later.')

        return self.api_success({'result': 'success'})

    def post_advanced_settings(self, request, user, data):
        """
        Update store's advanced settings. The settings include store's default shipping, return policies, etc.
        """
        data = data.dict()
        store_id = data.pop('store')

        if not store_id:
            return self.api_error('Missing a required store parameter.')

        store = get_object_or_404(GoogleStore, id=store_id)
        permissions.user_can_edit(user, store)

        pusher_channel = f'user_{user.id}'
        google_prefix = GoogleUtils(user).get_google_prefix(store.store_instance_id)
        request_data = {f"{google_prefix}_{k.replace('_', '')}": v for k, v in data.items()}

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
        Revoke google authorization and delete the google store and all connected models.
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
            store = GoogleStore.objects.get(pk=store_id)
        except GoogleStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        permissions.user_can_delete(user, store)

        # Delete auth token on SureDone
        google_utils = GoogleUtils(user)
        # TODO: revoke an auth token from SureDone once SureDone adds an API support for it
        # sd_auth_channel_resp = google_utils.api.remove_google_channel_auth(store.store_instance_id)

        # Disable the channel on SureDone
        sd_disable_store_resp = google_utils.disable_plugin_store(store.filter_instance_id)
        try:
            sd_disable_store_resp.raise_for_status()
            sd_disable_store_resp = sd_disable_store_resp.json()
        except HTTPError:
            capture_exception(extra={
                'message': 'Failed to disable a Google store on SureDone',
                'store_id': store.id,
                'user_id': user.id,
                'sd_response_status': sd_disable_store_resp.status_code,
                'sd_response_reason': sd_disable_store_resp.reason,
                'sd_response_data': sd_disable_store_resp.json(),
            })
            return self.api_error('Failed to remove the Google channel. Please try again'
                                  ' or contact support@dropified.com')

        # If failed to disable the google instance
        if sd_disable_store_resp.get('result') != 'success':
            return self.api_error('Failed to remove the Google channel. Please try again'
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
            store = GoogleStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except GoogleStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        resp = None
        try:
            resp = GoogleUtils(user).api.refresh_google_profiles(instance_id=store.filter_instance_id)
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
        Search google categories related to a keyword.
        For example, find all categories corresponding to the 'book' keyword

        :param request:
        :param user:
        :param data: API request parameters containing values for:
            search_term (str): A keyword for which to find google categories
            store_index (int): An index of the google store instance to use for the google API request
        :return: Categories found by the SureDone API
        :rtype: JsonResponse
        """
        search_term = data.get('search_term')
        if not search_term:
            self.api_error('Search term cannot be empty', status=404)
        return self.api_success({
            'data': GoogleUtils(user).search_categories(search_term)
        })

    def post_product_export(self, request, user, data):
        """
        Publish a product to google

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

        store = get_object_or_404(GoogleStore, id=store_id)
        permissions.user_can_view(user, store)
        if not user.can('send_to_Google.sub', store):
            raise PermissionDenied()

        if not user.can('send_to_store.use'):
            raise PermissionDenied()

        try:
            product = GoogleProduct.objects.get(guid=parent_guid)
        except GoogleProduct.DoesNotExist:
            return self.api_error('Product does not exist.')
        else:
            permissions.user_can_view(user, product)

        if product.source_id and product.store.id == store.id:
            return self.api_error('Product already connected to a Google store.')

        tasks.product_export.apply_async(kwargs={
            'user_id': user.id,
            'parent_guid': parent_guid,
            'store_id': store_id,
            'pusher_channel': f'user_{user.id}',
        }, countdown=0, expires=120)

        pusher = {'key': settings.PUSHER_KEY, 'channel': store.pusher_channel()}
        return self.api_success({'pusher': pusher})

    def post_product_update(self, request, user, data):
        """
        Update an existing product on SureDone and push updates to Google

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
        store = get_object_or_404(GoogleStore, id=store_id)
        product = get_object_or_404(GoogleProduct, guid=parent_guid)
        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)

        pusher_channel = f'user_{user.id}'
        sd_pusher = SureDonePusher(pusher_channel)
        default_event = 'fb-product-update'
        update_product_limit_check, product_limit_check, logs_count = GoogleUtils(user).check_product_update_limit(
            sd_pusher, default_event)
        if update_product_limit_check == "Limit Reached":
            return self.api_error(f'Your current plan allows up to {product_limit_check} product update(s).'
                                  f' Currently you have {logs_count} updated products.', status=401)

        tasks.product_update.apply_async(kwargs={
            'user_id': user.id,
            'parent_guid': parent_guid,
            'product_data': product_data,
            'store_id': store_id,
            'skip_publishing': skip_publishing,
            'pusher_channel': pusher_channel,
        }, countdown=0, expires=120)
        pusher = {'key': settings.PUSHER_KEY, 'channel': store.pusher_channel()}
        return self.api_success({'pusher': pusher})

    def get_products_info(self, request, user, data):
        products = {}
        for guid in data.getlist('products[]'):
            try:
                product = GoogleProduct.objects.get(guid=guid)
                permissions.user_can_view(user, product)

                products[guid] = json.loads(product.data)
            except GoogleProduct.DoesNotExist:
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
            product = GoogleProduct.objects.get(guid=parent_guid)
        except GoogleProduct.DoesNotExist:
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
            product = GoogleProduct.objects.get(guid=parent_sku)
        except GoogleProduct.DoesNotExist:
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

        product = get_object_or_404(GoogleProduct, guid=guid)
        permissions.user_can_edit(user, product)

        product.notes = data.get('notes')
        product.save()

        return self.api_success()

    def post_supplier(self, request, user, data):
        original_link = remove_link_query(data.get('original-link'))
        if not original_link:
            return self.api_error('Original Link is not set', status=500)

        supplier_name = data.get('supplier-name')
        if not supplier_name:
            return self.api_error('Supplier Name is missing', status=422)

        supplier_url = remove_link_query(data.get('supplier-link', 'http://www.aliexpress.com/'))

        product_guid = data.get('product')

        if not product_guid:
            return self.api_error('Product ID is missing', status=422)

        supplier_id = data.get('export', None)

        try:
            product = GoogleProduct.objects.filter(guid=product_guid).first()
            if not product:
                product_variant = GoogleProductVariant.objects.get(guid=product_guid)
                product = product_variant.parent_product

            permissions.user_can_edit(user, product)
            store = product.store

            if not store:
                return self.api_error('Google store not found', status=404)

        except (GoogleProduct.DoesNotExist, GoogleProductVariant.DoesNotExist):
            product_title = data.get('product-title') or 'Google Product'
            product_image = data.get('product-image')
            product_price = data.get('product-price')
            product_attributes = data.get('product-attributes')
            store_id = data.get('google-store')

            try:
                store = GoogleStore.objects.get(pk=store_id)
                permissions.user_can_view(user, store)
            except GoogleStore.DoesNotExist:
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
            google_utils = GoogleUtils(user)
            resp = google_utils.new_product_save(product_data, store, notes)

            if not isinstance(resp, dict) or resp.get('api_response', {}).get('1', {}).get('result') != 'success':
                capture_message(
                    'Error connecting a Google supplier.',
                    extra={
                        'guid': product_guid,
                        'sd_api_response': resp,
                        'user_id': user.id,
                        'store_id': store.id,
                    }
                )
                return self.api_error('Failed to connect the product. Please try again later.', status=400)

            product = GoogleProduct.objects.get(guid=product_guid)
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

        if not original_link:
            return self.api_error('Original Link is not set', status=500)

        # move product to the new store if its current one is inactive
        store_id = data.get('google-store')
        current_store = GoogleStore.objects.filter(id=store_id).first()
        if not store.is_active and current_store and current_store.is_active:
            google_utils = GoogleUtils(user)
            updated_product = google_utils.move_product_to_store(product, current_store, skip_all_channels=True)
            if updated_product:
                product = updated_product
                store = current_store

        reload = False
        try:
            product_supplier = GoogleSupplier.objects.get(id=supplier_id, store__in=user.profile.get_google_stores())

            product_supplier.product = product
            product_supplier.product_url = original_link
            product_supplier.supplier_name = supplier_name
            product_supplier.supplier_url = supplier_url
            product_supplier.save()

        except (ValueError, GoogleSupplier.DoesNotExist):
            reload = True
            is_default = not product.have_supplier()

            product_supplier = GoogleSupplier.objects.create(
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

        product = get_object_or_404(GoogleProduct, guid=product_guid)
        permissions.user_can_edit(user, product)

        try:
            supplier = GoogleSupplier.objects.get(id=supplier_id, product=product)
        except GoogleSupplier.DoesNotExist:
            return self.api_error('Supplier not found.\nPlease reload the page and try again.')

        product.set_default_supplier(supplier, commit=True)

        return self.api_success()

    def delete_supplier(self, request, user, data):
        product_guid = data.get('product')
        supplier_id = data.get('supplier')

        product = get_object_or_404(GoogleProduct, guid=product_guid)
        permissions.user_can_edit(user, product)

        try:
            supplier = GoogleSupplier.objects.get(id=supplier_id, product=product)
        except GoogleSupplier.DoesNotExist:
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
            board = GoogleBoard.objects.get(id=data.get('board'))
            permissions.user_can_edit(user, board)

        except GoogleBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)

        product_ids = data.getlist('products[]')
        products = GoogleProduct.objects.filter(guid__in=product_ids)

        for product in products:
            permissions.user_can_edit(user, product)

        board.products.add(*products)

        return self.api_success()

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def post_product_board(self, request, user, data):
        try:
            product = GoogleProduct.objects.get(guid=data.get('product'))
            permissions.user_can_edit(user, product)
        except GoogleProduct.DoesNotExist:
            return self.api_error('Product not found.', status=404)

        if data.get('board') == '0':
            product.boards.clear()
            product.save()
            return self.api_success()
        else:
            try:
                board = GoogleBoard.objects.get(id=data.get('board'))
                permissions.user_can_edit(user, board)
                board.products.add(product)
                board.save()
                return self.api_success({'board': {'id': board.id, 'title': board.title}})
            except GoogleBoard.DoesNotExist:
                return self.api_error('Board not found.', status=404)

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def delete_board_products(self, request, user, data):
        try:
            pk = safe_int(dict_val(data, ['board', 'board_id']))
            board = GoogleBoard.objects.get(pk=pk)
            permissions.user_can_edit(user, board)

        except GoogleBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)

        product_ids = data.getlist('products[]')
        products = GoogleProduct.objects.filter(guid__in=product_ids)
        for product in products:
            permissions.user_can_edit(user, product)
            board.products.remove(product)

        return self.api_success()

    def delete_board(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        try:
            pk = safe_int(data.get('board_id'))
            board = GoogleBoard.objects.get(pk=pk)
        except GoogleBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)
        else:
            permissions.user_can_delete(user, board)
            board.delete()
            return self.api_success()

    def get_order_notes(self, request, user, data):
        store = GoogleStore.objects.get(id=data['store'])
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
            store = GoogleStore.objects.get(id=store_id)
        except GoogleStore.DoesNotExist:
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

        google_utils = GoogleUtils(user)
        provider_name = google_utils.get_shipping_carrier_name(provider_id)

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
            r = google_utils.api.update_order_details(order_id, api_request_data)
            api_results = r.json().get('results')
            r.raise_for_status()
        except:
            capture_exception(level='warning', extra={'response': r.text if r else ''})
            message = 'Google API Error. Please try again.'
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
            store = GoogleStore.objects.get(id=safe_int(store_id))
        except GoogleStore.DoesNotExist:
            capture_exception()
            return self.api_error(f'Store {store_id} not found', status=404)

        if not user.can('place_orders.sub', store):
            raise PermissionDenied()

        permissions.user_can_view(user, store)

        if not item_sku:
            filters = {
                'oid': order_id
            }
            order = GoogleOrderListQuery(user, store, params=filters).items()[0]
            for item in order.items:
                if GoogleProductVariant.objects.filter(guid=item.get('id')):
                    item_sku.append(item.get('id'))

        order_updater = GoogleOrderUpdater(user, store, order_id)

        for line_id in item_sku:
            tracks = GoogleOrderTrack.objects.filter(store=store,
                                                     order_id=order_id,
                                                     line_id=line_id)
            tracks_count = tracks.count()

            if tracks_count > 1:
                tracks.delete()

            if tracks_count == 1:
                saved_track = tracks.first()

                if saved_track.source_id and source_id != saved_track.source_id:
                    return self.api_error('This order already has a supplier order ID', status=422)

            seen_source_orders = GoogleOrderTrack.objects.filter(store=store, source_id=source_id)
            seen_source_orders = seen_source_orders.values_list('order_id', flat=True)

            if len(seen_source_orders) and int(order_id) not in seen_source_orders and not data.get('forced'):
                return self.api_error('Supplier order ID is linked to another order', status=409)

            track, created = GoogleOrderTrack.objects.update_or_create(
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
            store = GoogleStore.objects.get(pk=safe_int(data['store']))
            if not user.can('place_orders.sub', store):
                raise PermissionDenied()

        try:
            order = GoogleOrderTrack.objects.get(id=data.get('order'))
            permissions.user_can_edit(user, order)
        except GoogleOrderTrack.DoesNotExist:
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
        orders = GoogleOrderTrack.objects.filter(user=user.models_user, order_id=order_id, line_id=line_id)
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
            store = GoogleStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        order_id = data['order_id']
        note = data['note']

        if note is None:
            return self.api_error('Note required')

        latest_note = GoogleUtils(user).get_latest_order_note(order_id)
        if latest_note == note:
            return self.api_success()
        else:
            try:
                resp = GoogleOrderUpdater(user, store, order_id).add_order_note(order_id, note)
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
            store = GoogleStore.objects.get(id=data.get('store'))
        except GoogleStore.DoesNotExist:
            return self.api_error('Store not found', status=404)
        try:
            product = GoogleProduct.objects.get(guid=parent_guid)
        except GoogleProduct.DoesNotExist:
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

    def post_products_supplier_sync(self, request, user, data):
        try:
            store = GoogleStore.objects.get(id=data.get('store'))
            permissions.user_can_edit(user, store)
        except GoogleStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        products = [product for product in data.get('products').split(',') if product]
        if not products:
            return self.api_error('No selected products to sync', status=422)

        user_store_supplier_sync_key = f'user_store_supplier_sync_{user.id}_{store.id}'
        if cache.get(user_store_supplier_sync_key) is not None:
            return self.api_error('Sync in progress', status=404)
        sync_price = data.get('sync_price', False)
        price_markup = safe_float(data['price_markup'])
        compare_markup = safe_float(data['compare_markup'])
        sync_inventory = data.get('sync_inventory', False)
        task = tasks.products_supplier_sync.apply_async(
            args=[store.id, user.id, products, sync_price, price_markup, compare_markup, sync_inventory,
                  user_store_supplier_sync_key], expires=180)
        cache.set(user_store_supplier_sync_key, task.id, timeout=3600)
        return self.api_success({'task': task.id})

    def post_products_supplier_sync_stop(self, request, user, data):
        try:
            store = GoogleStore.objects.get(id=data.get('store'))
            permissions.user_can_edit(user, store)
        except GoogleStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        user_store_supplier_sync_key = f'user_store_supplier_sync_{user.id}_{store.id}'
        task_id = cache.get(user_store_supplier_sync_key)
        if task_id is not None:
            celery_app.control.revoke(task_id, terminate=True)
            cache.delete(user_store_supplier_sync_key)
            return self.api_success()
        return self.api_error('No Sync in progress', status=404)

    def get_product_latest_relist_log(self, request, user, data):
        parent_guid = data.get('product')
        if not parent_guid:
            return self.api_error('Product ID cannot be empty.')

        store_id = data.get('store')
        if not store_id:
            return self.api_error('Store ID cannot be empty.')

        pusher_channel = f'user_{user.id}'
        tasks.product_latest_relist_log.apply_async(kwargs={
            'user_id': user.id,
            'parent_guid': parent_guid,
            'store_id': store_id,
            'pusher_channel': pusher_channel,
        }, countdown=0, expires=120)

        pusher = {'key': settings.PUSHER_KEY, 'channel': pusher_channel}
        return self.api_success({'pusher': pusher})
