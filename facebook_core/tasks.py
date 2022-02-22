from json import JSONDecodeError
from requests.exceptions import HTTPError

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.template.defaultfilters import truncatewords
from django.urls import reverse

from app.celery_base import CaptureFailure, celery_app, retry_countdown
from lib.exceptions import capture_exception
from shopified_core import permissions
from shopified_core.utils import get_domain, http_exception_response, http_excption_status_code, safe_json
from suredone_core.models import SureDoneAccount
from suredone_core.utils import SureDonePusher

from .models import FBProduct, FBStore
from .utils import FBOrderUpdater, FBUtils, smart_board_by_product


@celery_app.task(base=CaptureFailure)
def add_new_fb_store(sd_account_id, pusher_channel, user_id, instance_id=None, event_name=None, error_message=None):
    user = User.objects.get(id=user_id)
    sd_pusher = SureDonePusher(pusher_channel)
    default_event = 'fb-store-add' if event_name is None else event_name
    if error_message is not None:
        default_error_message = error_message
    else:
        default_error_message = 'Failed to add a new Facebook channel. ' \
                                'Please try again or contact support@dropified.com'

    try:
        sd_account = SureDoneAccount.objects.get(id=sd_account_id)

        # Step 1: Find a channel to authorize
        fb_utils = FBUtils(user, account_id=sd_account.id)
        next_instance_id = fb_utils.find_next_instance_to_authorize()

        # Step 2: Create a new instance
        created_instance_id = fb_utils.create_new_fb_store_instance(next_instance_id)

        # Step 3: Get Auth URL
        auth_url = fb_utils.get_auth_url(created_instance_id)

        if not auth_url:
            raise HTTPError('Invalid auth_url returned from SureDone')

        sd_pusher.trigger(default_event, {
            'success': True,
            'auth_url': auth_url,
        })

        return sd_account_id
    except Exception:
        sd_pusher.trigger(default_event, {
            'success': False,
            'error': default_error_message,
        })


@celery_app.task(base=CaptureFailure)
def update_profile_settings(user_id, store_id, data, pusher_channel, event_name=None):
    pusher_event = event_name if event_name else 'fb-advanced-settings-update'
    sd_pusher = SureDonePusher(pusher_channel)
    try:
        user = User.objects.get(id=user_id)
        store = FBStore.objects.get(id=store_id)

        permissions.user_can_edit(user, store)
        fb_utils = FBUtils(user)

        # Update fb settings
        resp = None
        try:
            resp = fb_utils.api.update_user_settings(data)
            resp.raise_for_status()
        except HTTPError:
            try:
                resp_body = resp.json()
                error_message = resp_body.get('message')
            except JSONDecodeError:
                error_message = None
            error_message = error_message if error_message else 'Unknown Issue'
            sd_pusher.trigger(pusher_event, {
                'success': False,
                'store_id': store_id,
                'error': f'Failed to update store settings.\nError: {error_message}.'
            })
            return

        sd_pusher.trigger(pusher_event, {
            'success': True,
            'store_id': store_id,
        })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        sd_pusher.trigger(pusher_event, {
            'success': False,
            'error': http_exception_response(e, json=True).get('message', 'Server Error'),
            'store_id': store_id,
        })


@celery_app.task(base=CaptureFailure)
def product_save(req_data, user_id, pusher_channel):
    sd_pusher = SureDonePusher(pusher_channel)
    default_event = 'fb-product-save'

    try:
        user = User.objects.get(id=user_id)
        store = req_data.get('store')
        product_data = req_data.get('data')

        # 1. Get store
        if store:
            try:
                store = FBStore.objects.get(id=store)
                permissions.user_can_view(user, store)

            except (FBStore.DoesNotExist, ValueError):
                capture_exception()
                sd_pusher.trigger(default_event, {
                    'success': False,
                    'error': f'Selected store ({store}) not found'
                })
                return
            except PermissionDenied as e:
                sd_pusher.trigger(default_event, {
                    'success': False,
                    'error': f'Store: {e}'
                })
                return
        else:
            store = user.profile.get_fb_stores().first()

        # 2. Load and verify product data
        if not product_data:
            sd_pusher.trigger(default_event, {
                'success': False,
                'error': 'Product data cannot be empty.'
            })
            return

        if isinstance(product_data, str):
            product_data = safe_json(product_data)
            if not product_data:
                sd_pusher.trigger(default_event, {
                    'success': False,
                    'error': 'Product data cannot be empty.'
                })
                return

        # 3. Verify and compute original URL
        original_url = product_data.get('original_url')

        if not original_url:
            original_url = req_data.get('original_url')
        try:
            import_store = get_domain(original_url)
        except:
            capture_exception(extra={'original_url': original_url})

            sd_pusher.trigger(default_event, {
                'success': False,
                'error': 'Original URL is not set.'
            })
            return

        if not import_store or not user.can(f'{import_store}_import.use'):
            if not import_store:
                import_store = 'N/A'

            if not user.can('import_from_any.use'):
                sd_pusher.trigger(default_event, {
                    'success': False,
                    'error': f'Importing from this store ({import_store}) is not included in your current plan.'
                })
                return

        # TODO: Add modifying an existing product
        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)

        if not can_add:
            sd_pusher.trigger(default_event, {
                'success': False,
                'error': "Woohoo! 🎉. You are growing and you've hit your account limit for products. "
                         "Upgrade your plan to keep importing new products"
            })
            return

        result = FBUtils(user).product_save_draft(product_data,
                                                  store,
                                                  req_data.get('notes'),
                                                  req_data.get('activate'))

        if not result:
            sd_pusher.trigger(default_event, {
                'success': False,
                'error': "Something went wrong. Please try again."
            })
            return

        product_guid = result.get('parent_guid', '')
        url = reverse('fb:product_detail', kwargs={'pk': product_guid, 'store_index': store.pk})

        sd_pusher.trigger(default_event, {
            'success': True,
            'product': {
                'url': url,
                'id': product_guid,
            }
        })

    except ValueError as e:
        sd_pusher.trigger(default_event, {
            'success': False,
            'error': f'Param {e.args[1]}: {e.args[0]}'
        })


@celery_app.task(base=CaptureFailure)
def product_export(user_id, parent_guid, store_id, pusher_channel):
    user = User.objects.get(id=user_id)
    store = FBStore.objects.get(id=store_id)
    product = FBProduct.objects.get(guid=parent_guid)
    sd_pusher = SureDonePusher(pusher_channel)
    pusher_event = 'fb-product-export'
    try:
        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)
        fb_utils = FBUtils(user)

        variant_guids = product.product_variants.all().values_list('guid', flat=True)
        api_response = fb_utils.relist_product(variant_guids, 'facebook', store.store_instance_id)
        # Get error message for each non-successful request
        api_error_messages = {i: api_response.get(f'{i}', {}).get('errors')
                              for i in range(1, api_response.get('actions', 1) + 1)
                              if api_response.get(f'{i}', {}).get('result') != 'success'}

        if len(api_error_messages):
            sd_pusher.trigger(pusher_event, {
                'success': False,
                'product': product.guid,
                'error': fb_utils.format_error_messages_by_variant(api_error_messages)
            })
            return

        sd_pusher.trigger(pusher_event, {
            'success': True,
            'product': product.guid,
            'product_url': reverse('fb:product_detail', kwargs={'pk': parent_guid, 'store_index': store.pk}),
        })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        sd_pusher.trigger(pusher_event, {
            'success': False,
            'error': http_exception_response(e, json=True).get('message', 'Server Error'),
            'product': product.guid,
            'product_url': reverse('fb:product_detail', kwargs={'pk': parent_guid, 'store_index': store.pk})
        })


@celery_app.task(base=CaptureFailure)
def product_update(user_id, parent_guid, product_data, store_id, skip_publishing, pusher_channel):
    user = User.objects.get(id=user_id)
    store = FBStore.objects.get(id=store_id)
    product = FBProduct.objects.get(guid=parent_guid)
    default_error_message = 'Something went wrong, please try again.'
    sd_pusher = SureDonePusher(pusher_channel)
    pusher_event = 'fb-product-update'
    try:
        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)
        fb_utils = FBUtils(user)

        product_data['dropifiedconnectedstoreid'] = store.store_instance_id

        # Remap category fields to SureDone conventions
        fb_cat_id = product_data.pop('fb_category_id', None)
        fb_prefix = fb_utils.get_fb_prefix(store.store_instance_id)
        if fb_cat_id:
            product_data[f'{fb_prefix}category'] = fb_cat_id

        product_data['dropifiedfbproductlink'] = product_data.pop('page_link', '')

        sd_api_response = fb_utils.update_product_details(product_data, 'facebook', store.store_instance_id,
                                                          skip_all_channels=skip_publishing)

        url = reverse('fb:product_detail', kwargs={'pk': product.guid, 'store_index': store.pk})

        # If the product was not successfully posted
        error_msg = fb_utils.format_error_messages('actions', sd_api_response)
        if error_msg:
            sd_pusher.trigger(pusher_event, {
                'success': False,
                'error': error_msg,
                'product': product.guid,
                'product_url': url
            })
            return

        # Fetch SureDone updates and update the DB
        updated_product = fb_utils.get_fb_product_details(parent_guid, smart_board_sync=True)

        # If the SureDone returns no data, then the product did not get imported
        if not updated_product or not isinstance(updated_product, FBProduct):
            sd_pusher.trigger(pusher_event, {
                'success': False,
                'error': default_error_message,
                'product': product.guid,
                'product_url': url
            })
            return

        sd_pusher.trigger(pusher_event, {
            'success': True,
            'product': product.guid,
            'product_url': url,
        })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        sd_pusher.trigger(pusher_event, {
            'success': False,
            'error': http_exception_response(e, json=True).get('message', 'Server Error'),
            'product': product.guid,
            'product_url': reverse('fb:product_detail', kwargs={'pk': product.guid, 'store_index': store.pk})
        })


@celery_app.task(base=CaptureFailure)
def product_duplicate(user_id, parent_sku, product_data, store_id):
    user = User.objects.get(id=user_id)
    store = FBStore.objects.get(id=store_id)
    pusher_event = 'product-duplicate'
    try:
        result = FBUtils(user).duplicate_product(product_data, store)

        if not result:
            store.pusher_trigger(pusher_event, {
                'success': False,
                'error': "Something went wrong. Please try again."
            })
            return

        product_guid = result.get('parent_guid', '')
        duplicated_product_url = reverse('fb:product_detail', kwargs={'pk': product_guid, 'store_index': store.pk})

        store.pusher_trigger(pusher_event, {
            'success': True,
            'product': parent_sku,
            'duplicated_product_url': duplicated_product_url,
        })

    except ValueError as e:
        store.pusher_trigger(pusher_event, {
            'success': False,
            'error': f'Param {e.args[1]}: {e.args[0]}'
        })


@celery_app.task(base=CaptureFailure)
def product_delete(user_id, parent_guid, store_id):
    user = User.objects.get(id=user_id)
    store = FBStore.objects.get(id=store_id)
    product = FBProduct.objects.get(guid=parent_guid)
    default_error_message = 'Something went wrong, please try again.'
    pusher_event = 'product-delete'
    try:
        permissions.user_can_delete(user, product)
        fb_utils = FBUtils(user)
        is_connected = product.is_connected
        sd_api_resp = fb_utils.delete_product_with_all_variations(parent_guid)

        if not isinstance(sd_api_resp, dict):
            store.pusher_trigger(pusher_event, {
                'success': False,
                'product': product.guid,
                'error': default_error_message
            })
            return

        err_msg = fb_utils.format_error_messages('actions', sd_api_resp)
        if err_msg:
            store.pusher_trigger(pusher_event, {
                'success': False,
                'product': product.guid,
                'error': err_msg or default_error_message
            })
            return

        if sd_api_resp.get('result') != 'success':
            store.pusher_trigger(pusher_event, {
                'success': False,
                'product': product.guid,
                'error': sd_api_resp.get('message') or default_error_message
            })
            return

        # Delete the product and its variants for the product
        product.delete()

        redirect_url = f"{reverse('fb:products_list')}?store={store.id if is_connected else 'n'}"

        store.pusher_trigger(pusher_event, {
            'success': True,
            'product': product.guid,
            'redirect_url': redirect_url,
        })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        store.pusher_trigger(pusher_event, {
            'success': False,
            'error': http_exception_response(e, json=True).get('message', 'Server Error'),
            'product': product.guid,
            'product_url': reverse('fb:product_detail', kwargs={'pk': parent_guid, 'store_index': store.pk})
        })


@celery_app.task(base=CaptureFailure)
def do_smart_board_sync_for_product(user_id, product_id):
    user = User.objects.get(id=user_id)
    product = FBProduct.objects.get(id=product_id)
    try:
        permissions.user_can_edit(user, product)
        smart_board_by_product(user, product)

    except Exception as e:
        capture_exception(extra={
            'message': 'Failed to perform the smart board sync task',
            'product_id': product_id,
            'error': e
        })


@celery_app.task(base=CaptureFailure)
def get_latest_order_note_task(user_id, store_id, order_ids):
    user = User.objects.get(id=user_id)
    store = FBStore.objects.get(pk=store_id)
    have_error = False

    for order_id in order_ids:
        data = {'order_id': order_id, 'success': False}

        if not have_error:
            try:
                data['success'] = True
                data['note'] = FBUtils(user).get_latest_order_note(order_id)

            except Exception as e:
                have_error = True
                if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
                    capture_exception(extra=http_exception_response(e))

        store.pusher_trigger('get-order-note', data)


@celery_app.task(base=CaptureFailure, bind=True)
def order_save_changes(self, data):
    order_id = None
    try:
        updater = FBOrderUpdater()
        updater.fromJSON(data)

        order_id = updater.order_id

        updater.save_changes()

        order_note = '\n'.join(updater.notes)
        updater.store.pusher_trigger('order-note-update', {
            'order_id': order_id,
            'note': order_note,
            'note_snippet': truncatewords(order_note, 10),
        })

    except Exception as e:
        if http_excption_status_code(e) in [401, 402, 403, 404]:
            return

        capture_exception(extra=http_exception_response(e))

        if not self.request.called_directly:
            countdown = retry_countdown(f'retry_ordered_tags_{order_id}', self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure)
def variant_image(user_id, parent_guid, guid, product_data, store_id, skip_publishing=True):
    store = FBStore.objects.get(id=store_id)
    default_error_message = 'Something went wrong, please try again.'
    pusher_event = 'variant-image'
    try:
        user = User.objects.get(id=user_id)
        product = FBProduct.objects.get(guid=parent_guid)

        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)
        fb_utils = FBUtils(user)

        sd_api_response = fb_utils.update_product_variant(product_data, skip_all_channels=skip_publishing)

        # If the product was not successfully posted
        error_msg = fb_utils.format_error_messages('actions', sd_api_response)
        if error_msg:
            store.pusher_trigger(pusher_event, {
                'success': False,
                'error': error_msg,
                'product': product.guid
            })
            return

        # Fetch SureDone updates and update the DB
        updated_product = fb_utils.get_fb_product_details(parent_guid, smart_board_sync=True)

        # If the SureDone returns no data, then the product did not get imported
        if not updated_product or not isinstance(updated_product, FBProduct):
            store.pusher_trigger(pusher_event, {
                'success': False,
                'error': default_error_message,
                'product': product.guid
            })
            return

        store.pusher_trigger(pusher_event, {
            'success': True,
            'product': product.guid
        })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        store.pusher_trigger(pusher_event, {
            'success': False,
            'error': http_exception_response(e, json=True).get('message', 'Server Error'),
            'product': product.guid
        })
