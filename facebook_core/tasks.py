from json import JSONDecodeError
from requests.exceptions import HTTPError

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.template.defaultfilters import truncatewords
from django.urls import reverse

from app.celery_base import CaptureFailure, celery_app, retry_countdown
from lib.exceptions import capture_exception, capture_message
from shopified_core import permissions
from shopified_core.utils import get_domain, http_exception_response, http_excption_status_code, safe_int, safe_json
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
        default_error_message = 'Failed to add a new eBay channel. Please try again or contact support@dropified.com'

    try:
        try:
            sd_account = SureDoneAccount.objects.get(id=sd_account_id)
        except SureDoneAccount.DoesNotExist:
            sd_pusher.trigger(default_event, {
                'success': False,
                'error': 'Something went wrong. Please try again.'
            })
            return

        # Step 1: Get all user options config
        fb_utils = FBUtils(user, account_id=sd_account.id)
        sd_config = fb_utils.get_all_user_options()
        fb_plugin_settings = safe_json(sd_config.get('plugin_settings', '{}')).get('channel', {}).get('fb', {})

        # Step 2: Find an instance to authorize
        if instance_id is not None:
            channel_inst_to_use = instance_id
        else:
            # Check if the default fb instance has already been authorized
            channel_inst_to_use = 1
            default_fb_token = sd_config.get('fb_token') or sd_config.get('fb_token_oauth')

            # If the user's default fb is already authorized, try finding an unauthorized channel from plugins list
            if default_fb_token:
                channel_inst_to_use = None

                # Parse plugin settings
                for inst_config in fb_plugin_settings.values():
                    inst_id = safe_int(inst_config.get('instanceId'), inst_config.get('instanceId'))
                    inst_prefix = fb_utils.get_fb_prefix(inst_id)
                    inst_token = sd_config.get(f'{inst_prefix}_token') or sd_config.get(f'{inst_prefix}_token_oauth')

                    # Found an unauthorized instance
                    if isinstance(inst_token, str) and len(inst_token) == 0:
                        channel_inst_to_use = inst_id
                        break

        # If the default and all additional fb plugins are already authorized, create a new fb instance
        if channel_inst_to_use is None:
            sd_add_inst_resp = fb_utils.api.add_new_fb_instance()

            # If failed to add a new fb instance
            try:
                sd_add_inst_resp.raise_for_status()
                resp_data = sd_add_inst_resp.json()

                if resp_data.get('result') != 'success':
                    capture_message('Request to add a new eBay store instance failed.', extra={
                        'suredone_account_id': sd_account_id,
                        'response_code': sd_add_inst_resp.status_code,
                        'response_reason': sd_add_inst_resp.reason,
                        'response_data': resp_data
                    })
                    sd_pusher.trigger(default_event, {
                        'success': False,
                        'error': default_error_message
                    })
                    return
            except Exception:
                capture_exception(extra={
                    'description': 'Error when trying to add a new fb instance to a SureDone account',
                    'suredone_account_id': sd_account_id,
                    'response_code': sd_add_inst_resp.status_code,
                    'response_reason': sd_add_inst_resp.reason,
                })
                sd_pusher.trigger(default_event, {
                    'success': False,
                    'error': default_error_message
                })
                return

            # Calculate the new fb instance ID without calling the SD API again
            # Each new channel ID is incremented by 1, therefore, the new ID is the largest ID + 1
            all_fb_ids = [safe_int(x.get('instanceId')) for x in fb_plugin_settings.values()]
            channel_inst_to_use = max(all_fb_ids) + 1 if all_fb_ids else 2
            channel_prefix = fb_utils.get_fb_prefix(channel_inst_to_use)
            instance_enabled = True
        else:
            channel_prefix = fb_utils.get_fb_prefix(channel_inst_to_use)
            instance_enabled = sd_config.get(f'site_{channel_prefix}connect', 'off') == 'on'

        # Step 3: Enable the channel instance if not enabled yet
        if not instance_enabled:
            sd_enable_channel_resp = fb_utils.api.update_user_settings({f'site_{channel_prefix}connect': 'on'})

            # If failed to enable the fb channel instance
            try:
                sd_enable_channel_resp.raise_for_status()
                resp_data = sd_enable_channel_resp.json()

                if resp_data.get('result') != 'success':
                    capture_message('Request to enable an eBay store instance failed.', extra={
                        'suredone_account_id': sd_account_id,
                        'store_instance_id': channel_inst_to_use,
                        'response_code': sd_enable_channel_resp.status_code,
                        'response_reason': sd_enable_channel_resp.reason,
                        'response_data': resp_data
                    })
                    sd_pusher.trigger(default_event, {
                        'success': False,
                        'error': default_error_message
                    })
                    return
            except Exception:
                capture_exception(extra={
                    'description': 'Error when trying to enable an Facebook instance on a SureDone account',
                    'suredone_account_id': sd_account_id,
                    'store_instance_id': channel_inst_to_use,
                    'response_code': sd_enable_channel_resp.status_code,
                    'response_reason': sd_enable_channel_resp.reason,
                })
                sd_pusher.trigger(default_event, {
                    'success': False,
                    'error': default_error_message
                })
                return

        # Step 4: Get an fb authorization url
        sd_api_request_data = {'instance': channel_inst_to_use}
        sd_auth_channel_resp = fb_utils.api.authorize_fb_channel(sd_api_request_data, legacy=True)
        try:
            sd_auth_channel_resp.raise_for_status()
            resp_data = sd_auth_channel_resp.json()

            sd_resp_results = resp_data.get('results', {})
            sd_auth_url = sd_resp_results.get('successful', {}).get('auth_url')

            # If failed to get an fb channel authorization url
            if not sd_auth_url:
                capture_message('Received errors when requesting a SureDone eBay authorization url.', extra={
                    'suredone_account_id': sd_account_id,
                    'store_instance_id': channel_inst_to_use,
                    'response_code': sd_auth_channel_resp.status_code,
                    'response_reason': sd_auth_channel_resp.reason,
                    'response_data': resp_data
                })
                sd_pusher.trigger(default_event, {
                    'success': False,
                    'error': default_error_message
                })
                return
        except Exception:
            capture_exception(extra={
                'description': 'Error when trying to parse a SureDone eBay authorization response.',
                'suredone_account_id': sd_account_id,
                'store_instance_id': channel_inst_to_use,
                'response_code': sd_auth_channel_resp.status_code,
                'response_reason': sd_auth_channel_resp.reason,
            })
            sd_pusher.trigger(default_event, {
                'success': False,
                'error': default_error_message
            })
            return

        sd_pusher.trigger(default_event, {
            'success': True,
            'auth_url': sd_auth_url
        })
        return sd_account_id
    except:
        sd_pusher.trigger(default_event, {
            'success': False,
            'error': 'Something went wrong. Please contact Dropifed support.'
        })


@celery_app.task(base=CaptureFailure)
def get_advanced_options(user_id, store_id, pusher_channel, event_name=None):
    pusher_event = event_name if event_name else 'fb-advanced-settings-load'
    sd_pusher = SureDonePusher(pusher_channel)
    try:
        store = FBStore.objects.get(id=store_id)
        user = User.objects.get(id=user_id)

        permissions.user_can_view(user, store)
        fb_utils = FBUtils(user)

        # refresh fb profiles before getting all options
        resp = None
        try:
            resp = fb_utils.api.refresh_fb_profiles(instance_id=store.filter_instance_id)
            resp.raise_for_status()
        except HTTPError:
            try:
                resp_body = resp.json()
                error_message = resp_body.get('message')
                if 'Token does not match' in error_message:
                    error_message = 'Please reauthorize the store'
            except JSONDecodeError:
                error_message = None
            error_message = error_message if error_message else 'Unknown Issue'
            sd_pusher.trigger(pusher_event, {
                'success': False,
                'store_id': store_id,
                'error': f'API credentials are not correct\nError: {error_message}.'
            })
            return

        all_options = fb_utils.get_all_user_options()
        if not isinstance(all_options, dict):
            sd_pusher.trigger(pusher_event, {
                'success': False,
                'store_id': store_id,
                'error': 'Failed to get eBay options. Please try again.'
            })
            return

        fb_prefix = fb_utils.get_fb_prefix(store.store_instance_id)
        fb_config = safe_json(all_options.get(f'{fb_prefix}_attribute_mapping'))
        fb_site_id = all_options.get(f'{fb_prefix}_siteid')
        fb_site_id_options = [
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
        if not fb_config:
            sd_pusher.trigger(pusher_event, {
                'success': False,
                'store_id': store_id,
                'error': 'No eBay options found. Please try again.'
            })
            return

        profile_options = fb_config.get('profile', {})

        sd_pusher.trigger(pusher_event, {
            'success': True,
            'store_id': store_id,
            'options': {
                'payment_profile_options': list(profile_options.get('payment', {}).values()),
                'return_profile_options': list(profile_options.get('return', {}).values()),
                'shippping_profile_options': list(profile_options.get('shipping', {}).values()),
                'site_id_options': fb_site_id_options,
            },
            'settings': {
                'payment_profile_id': fb_config.get('paymentprofileid', ''),
                'return_profile_id': fb_config.get('returnprofileid', ''),
                'shipping_profile_id': fb_config.get('shippingprofileid', ''),
                'fb_siteid': fb_site_id,
            },
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
