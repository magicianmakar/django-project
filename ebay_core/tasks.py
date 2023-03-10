from json import JSONDecodeError
from math import ceil
from requests.exceptions import HTTPError

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.template.defaultfilters import truncatewords
from django.urls import reverse

from app.celery_base import CaptureFailure, celery_app, retry_countdown
from lib.exceptions import capture_exception, capture_message
from product_alerts.utils import get_supplier_variants, variant_index_from_supplier_sku
from shopified_core import permissions
from shopified_core.utils import get_domain, http_exception_response, http_excption_status_code, safe_int, safe_json
from suredone_core.models import SureDoneAccount
from suredone_core.utils import GetSureDoneProductByGuidEmpty, SureDonePusher

from .models import EbayProduct, EbayStore
from .utils import EbayOrderUpdater, EbayUtils, get_ebay_currencies_list, get_ebay_store_specific_currency_options, smart_board_by_product

EBAY_API_TIMEOUT = 120


@celery_app.task(base=CaptureFailure)
def add_new_ebay_store(sd_account_id, pusher_channel, user_id, instance_id=None, event_name=None, error_message=None):
    user = User.objects.get(id=user_id)
    sd_pusher = SureDonePusher(pusher_channel)
    default_event = 'ebay-store-add' if event_name is None else event_name
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
        ebay_utils = EbayUtils(user, account_id=sd_account.id)
        sd_config = ebay_utils.get_all_user_options()
        ebay_plugin_settings = safe_json(sd_config.get('plugin_settings', '{}')).get('channel', {}).get('ebay', {})

        # Step 2: Find an instance to authorize
        if instance_id is not None:
            channel_inst_to_use = instance_id
        else:
            # Check if the default ebay instance has already been authorized
            channel_inst_to_use = 1
            default_ebay_token = sd_config.get('ebay_token') or sd_config.get('ebay_token_oauth')

            # If the user's default ebay is already authorized, try finding an unauthorized channel from plugins list
            if default_ebay_token:
                channel_inst_to_use = None

                # Parse plugin settings
                for inst_config in ebay_plugin_settings.values():
                    inst_id = safe_int(inst_config.get('instanceId'), inst_config.get('instanceId'))
                    inst_prefix = ebay_utils.get_ebay_prefix(inst_id)
                    inst_token = sd_config.get(f'{inst_prefix}_token') or sd_config.get(f'{inst_prefix}_token_oauth')

                    # Found an unauthorized instance
                    if isinstance(inst_token, str) and len(inst_token) == 0:
                        channel_inst_to_use = inst_id
                        break

        # If the default and all additional ebay plugins are already authorized, create a new ebay instance
        if channel_inst_to_use is None:
            sd_add_inst_resp = ebay_utils.api.add_new_ebay_instance()

            # If failed to add a new ebay instance
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
                    'description': 'Error when trying to add a new ebay instance to a SureDone account',
                    'suredone_account_id': sd_account_id,
                    'response_code': sd_add_inst_resp.status_code,
                    'response_reason': sd_add_inst_resp.reason,
                })
                sd_pusher.trigger(default_event, {
                    'success': False,
                    'error': default_error_message
                })
                return

            # Calculate the new ebay instance ID without calling the SD API again
            # Each new channel ID is incremented by 1, therefore, the new ID is the largest ID + 1
            all_ebay_ids = [safe_int(x.get('instanceId')) for x in ebay_plugin_settings.values()]
            channel_inst_to_use = max(all_ebay_ids) + 1 if all_ebay_ids else 2
            channel_prefix = ebay_utils.get_ebay_prefix(channel_inst_to_use)
            instance_enabled = True
        else:
            channel_prefix = ebay_utils.get_ebay_prefix(channel_inst_to_use)
            instance_enabled = sd_config.get(f'site_{channel_prefix}connect', 'off') == 'on'

        # Step 3: Enable the channel instance if not enabled yet
        if not instance_enabled:
            sd_enable_channel_resp = ebay_utils.api.update_user_settings({f'site_{channel_prefix}connect': 'on'})

            # If failed to enable the ebay channel instance
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
                    'description': 'Error when trying to enable an ebay instance on a SureDone account',
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

        # Step 4: Get an ebay authorization url
        sd_api_request_data = {'instance': channel_inst_to_use}
        sd_auth_channel_resp = ebay_utils.api.authorize_ebay_channel(sd_api_request_data, legacy=True)
        resp_data = None
        try:
            resp_data = sd_auth_channel_resp.json()
            sd_auth_channel_resp.raise_for_status()

            sd_resp_results = resp_data.get('results', {})
            sd_auth_url = sd_resp_results.get('successful', {}).get('auth_url')

            # If failed to get an ebay channel authorization url
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
                'response_data': resp_data,
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
    except Exception as e:
        capture_exception(extra={
            'description': 'Error when trying to add a new eBay store.',
            'suredone_account_id': sd_account_id,
            'error': e,
        })
        sd_pusher.trigger(default_event, {
            'success': False,
            'error': 'Something went wrong. Please contact Dropified support.',
        })


@celery_app.task(base=CaptureFailure)
def sync_advanced_options(user_id, store_id, pusher_channel, event_name=None):
    pusher_event = event_name if event_name else 'ebay-business-policies-sync'
    sd_pusher = SureDonePusher(pusher_channel)
    try:
        store = EbayStore.objects.get(id=store_id)
        user = User.objects.get(id=user_id)

        permissions.user_can_view(user, store)
        ebay_utils = EbayUtils(user)

        # refresh ebay profiles before getting all options
        resp = None
        try:
            resp = ebay_utils.api.refresh_ebay_profiles(instance_id=store.filter_instance_id)
            resp.raise_for_status()
        except HTTPError:
            try:
                resp_body = resp.json()
                error_message = resp_body.get('message', '')
                if 'Token does not match' in error_message:
                    error_message = 'Please reauthorize the store'
            except JSONDecodeError:
                error_message = None
            error_message = error_message if error_message else 'Unknown Issue'
            sd_pusher.trigger(pusher_event, {
                'success': False,
                'store_id': store_id,
                'error': f'Failed to retrieve eBay business policies.\nError: {error_message}.'
            })
            return {'error': error_message}

        sd_pusher.trigger(pusher_event, {'success': True, 'store_id': store_id, 'status': 'Finished syncing.'})

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
    pusher_event = event_name if event_name else 'ebay-advanced-settings-update'
    sd_pusher = SureDonePusher(pusher_channel)
    try:
        user = User.objects.get(id=user_id)
        store = EbayStore.objects.get(id=store_id)

        permissions.user_can_edit(user, store)
        ebay_utils = EbayUtils(user)

        # Update ebay settings
        resp = None
        try:
            resp = ebay_utils.api.update_user_settings(data)
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
    default_event = 'ebay-product-save'

    try:
        user = User.objects.get(id=user_id)
        store = req_data.get('store')
        product_data = req_data.get('data')

        # 1. Get store
        if store:
            try:
                store = EbayStore.objects.get(id=store)
                permissions.user_can_view(user, store)

            except (EbayStore.DoesNotExist, ValueError):
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
            store = user.profile.get_ebay_stores().first()

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

        ebay_utils = EbayUtils(user, account_id=store.sd_account_id)

        # 4. Check currency settings
        original_data = req_data.get('original')
        if original_data:
            original_data = safe_json(original_data)
            original_currency = original_data.get('currency_code')
            ebay_currencies = [currency[0] for currency in get_ebay_currencies_list()]
            if store.currency_format and '{{ amount }}' in store.currency_format:
                store_currency = store.currency_format.replace('{{ amount }}', '')
                store_currency = [currency[0] for currency in get_ebay_store_specific_currency_options() if currency[2] == store_currency]
                if len(store_currency):
                    store_currency = store_currency[0]
            else:
                store_currency = ebay_utils.get_ebay_user_settings_config().get('site_currency')

            # We assume the product currency is the same as the store currency since we can't find the product currency
            if original_currency is None:
                original_currency = store_currency

            if store_currency and store_currency != original_currency:
                error = f'The current product currency ({original_currency}) and your eBay store currency ({store_currency}) are different!'
                sd_pusher.trigger(default_event, {
                    'success': False,
                    'error': error
                })
                return

            if original_currency not in ebay_currencies:
                ebay_currencies = ', '.join(ebay_currencies)
                error = f'{original_currency} is invalid currency for eBay, valid currencies are: {ebay_currencies}'
                sd_pusher.trigger(default_event, {
                    'success': False,
                    'error': error
                })
                return

            sd_account = SureDoneAccount.objects.get(id=store.sd_account_id)
            site_currency = sd_account.parsed_options_config.get('site_currency')

            if original_currency != site_currency:
                # Update currency settings on SureDone
                try:
                    ebay_utils.update_user_business_settings({'site_currency': original_currency})
                except:
                    sd_pusher.trigger(default_event, {
                        'success': False,
                        'error': 'Something went wrong, please try again.'
                    })
                    return

        # TODO: Add modifying an existing product
        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)

        if not can_add:
            sd_pusher.trigger(default_event, {
                'success': False,
                'error': "Woohoo! ????. You are growing and you've hit your account limit for products. "
                         "Upgrade your plan to keep importing new products"
            })
            return

        result = EbayUtils(user).product_save_draft(product_data,
                                                    store,
                                                    req_data.get('notes'),
                                                    req_data.get('activate'),
                                                    req_data.get('master_product'))

        if not result:
            sd_pusher.trigger(default_event, {
                'success': False,
                'error': "Something went wrong. Please try again."
            })
            return

        product_guid = result.get('parent_guid', '')
        url = reverse('ebay:product_detail', kwargs={'pk': product_guid, 'store_index': store.pk})

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
def product_export(user_id, parent_guid, store_id):
    user = User.objects.get(id=user_id)
    store = EbayStore.objects.get(id=store_id)
    product = EbayProduct.objects.get(guid=parent_guid)
    default_error_message = 'Something went wrong, please try again.'
    pusher_event = 'product-export'
    try:
        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)
        ebay_utils = EbayUtils(user)

        api_response = ebay_utils.relist_product([parent_guid], 'ebay', store.store_instance_id)
        api_error_message = api_response.get('1', {}).get('errors')
        if api_error_message:
            parsed_ebay_errors_list = ebay_utils.parse_ebay_errors(api_error_message)
        else:
            parsed_ebay_errors_list = None

        # Verify that the product got listed by fetching the product from SureDone
        store.pusher_trigger(pusher_event, {
            'product': product.guid,
            'progress': 'Verifying...',
            'error': False
        })
        updated_product = ebay_utils.get_ebay_product_details(parent_guid, add_model_fields={'store': store})
        # If the SureDone returns no data, then the product did not get exported
        if not updated_product or not isinstance(updated_product, EbayProduct):
            store.pusher_trigger(pusher_event, {
                'success': False,
                'product': product.guid,
                'error': api_error_message or default_error_message,
                'parsed_ebay_errors_list': parsed_ebay_errors_list,
                'product_url': reverse('ebay:product_detail', kwargs={'pk': parent_guid, 'store_index': store.pk}),
            })
            return

        error_message = ''

        # Verify the product and all variants actually got connected to the store
        if not updated_product.all_children_variants_are_connected:
            # Case #1: Only some variants got successfully exported
            if updated_product.some_variants_are_connected:
                message = '<b>An error occurred when exporting some variants to eBay</b>'
                if api_error_message:
                    error_message = f"{message}:\n{api_error_message}"
                else:
                    error_message = f'{message}, please try again.'
            else:
                # Case #2: None of the variants got successfully exported
                message = '<b>An error occurred when exporting the product to eBay</b>'
                if api_error_message:
                    error_message = f"{message}:\n{api_error_message}"
                    if 'Business country and postal code are required' in api_error_message:
                        url = f'{reverse("settings")}#ebay-settings'
                        error_message = f'{error_message}.\n\n Please configure the business country and postal code' \
                                        f' in <a href={url} target="_blank">eBay settings</a> and try again.'
                else:
                    error_message = f'{message}, please try again.'

        if error_message:
            store.pusher_trigger(pusher_event, {
                'success': False,
                'product': product.guid,
                'error': error_message,
                'parsed_ebay_errors_list': parsed_ebay_errors_list,
                'product_url': reverse('ebay:product_detail', kwargs={'pk': parent_guid, 'store_index': store.pk}),
            })
            return

        store.pusher_trigger(pusher_event, {
            'success': True,
            'product': product.guid,
            'product_url': reverse('ebay:product_detail', kwargs={'pk': parent_guid, 'store_index': store.pk}),
        })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        store.pusher_trigger(pusher_event, {
            'success': False,
            'error': http_exception_response(e, json=True).get('message', 'Server Error'),
            'product': product.guid,
            'product_url': reverse('ebay:product_detail', kwargs={'pk': parent_guid, 'store_index': store.pk})
        })


@celery_app.task(base=CaptureFailure)
def product_update(user_id, parent_guid, product_data, store_id, skip_publishing):
    user = User.objects.get(id=user_id)
    store = EbayStore.objects.get(id=store_id)
    product = EbayProduct.objects.get(guid=parent_guid)
    default_error_message = 'Something went wrong, please try again.'
    pusher_event = 'product-update'
    try:
        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)
        ebay_utils = EbayUtils(user)

        product_data['dropifiedconnectedstoreid'] = store.store_instance_id
        product_data['dropifiedinternalnotes'] = product.notes
        product_data['notes'] = product_data.get('condition')

        # Remap category fields to SureDone conventions
        ebay_cat_id = product_data.pop('ebay_category_id', None)
        ebay_prefix = ebay_utils.get_ebay_prefix(store.store_instance_id)
        if ebay_cat_id:
            product_data[f'{ebay_prefix}catid'] = ebay_cat_id

        # Update ebayitemspecifics keys to reflect the updated ebay store index
        if store.store_instance_id != 1:
            new_values = {}
            for key in product_data.keys():
                if 'ebayitemspecifics' in key:
                    new_key = key.replace('ebayitemspecifics', f'{ebay_prefix}itemspecifics')
                    new_values[new_key] = product_data.get(key)
                    new_values[key] = ''
            product_data.update(new_values)

            # Update variant-specific fields as well
            for variant in product_data.get('variants', []):
                new_values = {}
                for key in variant.keys():
                    if 'ebayitemspecifics' in key:
                        new_key = key.replace('ebayitemspecifics', f'{ebay_prefix}itemspecifics')
                        new_values[new_key] = variant.get(key)
                        new_values[key] = ''
                variant.update(new_values)

        # Get the old data to verify that no variations got deleted
        # TODO: handle variations modifications
        # parent_guid = product_data.get('guid')
        # old_product_data = ebay_utils.get_products_by_sku(parent_guid, paginate=False, sort='id')

        # Reformat images to SureDone conventions
        media = list(filter(None, product_data.pop('images', [])))
        mediax = []
        for i in range(10):
            if len(media) > i:
                product_data[f'media{i + 1}'] = media[i] if media[i] else ''
            else:
                product_data[f'media{i + 1}'] = ''
        if len(media) > 10:
            mediax = media[10:]
        product_data['mediax'] = '*'.join(mediax)

        # Fill images into variants
        for variant in product_data.get('variants', []):
            media1 = variant.pop('image')
            variant['media1'] = (media1 if variant['guid'] != variant['sku'] and media1 in media
                                 else product_data['media1'])
            for i in range(2, 11):
                if product_data.get(f'media{i}'):
                    variant[f'media{i}'] = product_data[f'media{i}']
            if product_data['mediax']:
                variant['mediax'] = product_data['mediax']

        sd_api_response = ebay_utils.update_product_details(product_data, 'ebay', store.store_instance_id,
                                                            skip_all_channels=skip_publishing)

        parsed_ebay_errors_list = []

        if product_data.get('status') != 'disable' and product_data.get('published') is False:
            api_response = ebay_utils.end_product([parent_guid], 'ebay', store.store_instance_id)
            api_error_message = api_response.get('1', {}).get('errors')
            if api_error_message:
                parsed_ebay_errors_list += ebay_utils.parse_ebay_errors(api_error_message)

        url = reverse('ebay:product_detail', kwargs={'pk': product.guid, 'store_index': store.pk})

        # If the product was not successfully posted
        error_msg = ebay_utils.format_error_messages('actions', sd_api_response)

        api_error_message = sd_api_response.get('1', {}).get('errors')
        if api_error_message:
            parsed_ebay_errors_list += ebay_utils.parse_ebay_errors(api_error_message)

        if error_msg:
            store.pusher_trigger(pusher_event, {
                'success': False,
                'error': error_msg,
                'product': product.guid,
                'product_url': url,
                'parsed_ebay_errors_list': parsed_ebay_errors_list
            })
            return

        # Fetch SureDone updates and update the DB
        updated_product = ebay_utils.get_ebay_product_details(parent_guid, smart_board_sync=True)

        # If the SureDone returns no data, then the product did not get imported
        if not updated_product or not isinstance(updated_product, EbayProduct):
            store.pusher_trigger(pusher_event, {
                'success': False,
                'error': default_error_message,
                'product': product.guid,
                'product_url': url
            })
            return

        store.pusher_trigger(pusher_event, {
            'success': True,
            'product': product.guid,
            'product_url': url,
        })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        store.pusher_trigger(pusher_event, {
            'success': False,
            'error': http_exception_response(e, json=True).get('message', 'Server Error'),
            'product': product.guid,
            'product_url': reverse('ebay:product_detail', kwargs={'pk': product.guid, 'store_index': store.pk})
        })


@celery_app.task(base=CaptureFailure)
def product_duplicate(user_id, parent_sku, product_data, store_id):
    user = User.objects.get(id=user_id)
    store = EbayStore.objects.get(id=store_id)
    pusher_event = 'product-duplicate'
    try:
        result = EbayUtils(user).duplicate_product(product_data, store)

        if not result or isinstance(result, dict) and result.get('error'):
            store.pusher_trigger(pusher_event, {
                'success': False,
                'error': result.get('error') if result else "Something went wrong. Please try again."
            })
            return

        product_guid = result.get('parent_guid', '')
        duplicated_product_url = reverse('ebay:product_detail', kwargs={'pk': product_guid, 'store_index': store.pk})

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
def product_delete(user_id, parent_guid, store_id, skip_all_channels=False):
    user = User.objects.get(id=user_id)
    store = EbayStore.objects.get(id=store_id)
    product = EbayProduct.objects.get(guid=parent_guid)
    default_error_message = 'Something went wrong, please try again.'
    pusher_event = 'product-delete'
    try:
        permissions.user_can_delete(user, product)
        ebay_utils = EbayUtils(user)
        is_connected = product.is_connected
        redirect_url = f"{reverse('ebay:products_list')}?store={store.id if is_connected else 'n'}"
        try:
            sd_api_resp = ebay_utils.delete_product_with_all_variations(parent_guid, skip_all_channels=skip_all_channels)
        except GetSureDoneProductByGuidEmpty:
            # Exception because the product is missing in SureDone
            # Delete the product and its variants for the product
            product.delete()
            store.pusher_trigger(pusher_event, {
                'success': True,
                'product': product.guid,
                'redirect_url': redirect_url,
            })
            return

        api_error_message = sd_api_resp.get('1', {}).get('errors')
        if api_error_message:
            parsed_ebay_errors_list = ebay_utils.parse_ebay_errors(api_error_message)
        else:
            parsed_ebay_errors_list = None

        if not isinstance(sd_api_resp, dict):
            store.pusher_trigger(pusher_event, {
                'success': False,
                'product': product.guid,
                'error': default_error_message
            })
            return

        err_msg = ebay_utils.format_error_messages('actions', sd_api_resp)
        if err_msg:
            store.pusher_trigger(pusher_event, {
                'success': False,
                'product': product.guid,
                'error': err_msg or default_error_message,
                'parsed_ebay_errors_list': parsed_ebay_errors_list
            })
            return

        if sd_api_resp.get('result') != 'success':
            store.pusher_trigger(pusher_event, {
                'success': False,
                'product': product.guid,
                'error': sd_api_resp.get('message') or default_error_message,
                'parsed_ebay_errors_list': parsed_ebay_errors_list
            })
            return

        # Delete the product and its variants for the product
        product.delete()

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
            'product_url': reverse('ebay:product_detail', kwargs={'pk': parent_guid, 'store_index': store.pk})
        })


@celery_app.task(base=CaptureFailure)
def delete_all_store_products(user_id, store_id, skip_all_channels=False):
    user = User.objects.get(id=user_id)
    try:
        ebay_utils = EbayUtils(user)
        products = EbayProduct.objects.filter(store_id=store_id).prefetch_related('product_variants')

        guids_to_delete = []
        for product in products:
            parent = None
            for variant in product.product_variants.all():
                if variant.is_main_variant:
                    parent = variant
                else:
                    guids_to_delete.append(variant.guid)
            # Don't add the parent to the list until all children are deleted
            # because otherwise SureDone will return an error on parent deletion
            if parent:
                guids_to_delete.append(parent.guid)

        batch_size = 100
        count = len(guids_to_delete)
        steps = ceil(count / batch_size)
        for step in range(0, steps):
            data = guids_to_delete[batch_size * step: count] \
                if step == steps - 1 else guids_to_delete[batch_size * step: batch_size * (step + 1)]

            api_response = ebay_utils.delete_products_by_guid(data, skip_all_channels)

            if isinstance(api_response, dict) and api_response.get('result') == 'success':
                EbayProduct.objects.filter(guid__in=data).delete()
            else:
                capture_message('Failed to delete products post store deletion', extra={
                    'data': data,
                    'suredone_response': api_response,
                    'suredone_user': ebay_utils.sd_account.api_username,
                    'step': step,
                    'total_batches': steps,
                })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))


@celery_app.task(base=CaptureFailure)
def do_smart_board_sync_for_product(user_id, product_id):
    user = User.objects.get(id=user_id)

    try:
        product = EbayProduct.objects.get(id=product_id)
    except EbayProduct.DoesNotExist:
        return

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
    store = EbayStore.objects.get(pk=store_id)
    have_error = False

    for order_id in order_ids:
        data = {'order_id': order_id, 'success': False}

        if not have_error:
            try:
                data['success'] = True
                data['note'] = EbayUtils(user).get_latest_order_note(order_id)

            except Exception as e:
                have_error = True
                if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
                    capture_exception(extra=http_exception_response(e))

        store.pusher_trigger('get-order-note', data)


@celery_app.task(base=CaptureFailure, bind=True)
def order_save_changes(self, data):
    order_id = None
    try:
        updater = EbayOrderUpdater()
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
def product_split(product_guid, split_factor, user_id):
    user = User.objects.get(id=user_id)
    product = EbayProduct.objects.get(guid=product_guid)
    default_error_message = 'Something went wrong, please try again.'
    pusher_event = 'product-split'
    can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)

    if not can_add:
        product.store.pusher.trigger(pusher_event, {
            'success': False,
            'error': "Woohoo! ????. You are growing and you've hit your account limit for products. "
                     "Upgrade your plan to keep importing new products"
        })
        return
    try:
        sd_api_resp = EbayUtils(user).split_product(product, split_factor)

        if not isinstance(sd_api_resp, dict):
            product.store.pusher_trigger(pusher_event, {
                'success': False,
                'product': product.guid,
                'error': default_error_message
            })
            return

        err_msg = EbayUtils(user).format_error_messages('actions', sd_api_resp)
        if err_msg:
            product.store.pusher_trigger(pusher_event, {
                'success': False,
                'product': product.guid,
                'error': err_msg or default_error_message
            })
            return

        if sd_api_resp.get('api_response', {}).get('result') != 'success':
            product.store.pusher_trigger(pusher_event, {
                'success': False,
                'product': product.guid,
                'error': sd_api_resp.get('message') or default_error_message
            })
            return

        redirect_url = f"{reverse('ebay:products_list')}?store=n"

        product.store.pusher_trigger(pusher_event, {
            'success': True,
            'product': product.guid,
            'redirect_url': redirect_url,
        })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        product.store.pusher_trigger(pusher_event, {
            'success': False,
            'error': http_exception_response(e, json=True).get('message', 'Server Error'),
            'product': product.guid,
            'product_url': reverse('ebay:product_detail', kwargs={'pk': product.guid, 'store_index': product.store.pk})
        })


@celery_app.task(base=CaptureFailure)
def variant_image(user_id, parent_guid, guid, product_data, store_id, skip_publishing=True):
    store = EbayStore.objects.get(id=store_id)
    default_error_message = 'Something went wrong, please try again.'
    pusher_event = 'variant-image'
    try:
        user = User.objects.get(id=user_id)
        product = EbayProduct.objects.get(guid=parent_guid)

        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)
        ebay_utils = EbayUtils(user)

        sd_api_response = ebay_utils.update_product_variant(product_data, skip_all_channels=skip_publishing)

        # If the product was not successfully posted
        error_msg = ebay_utils.format_error_messages('actions', sd_api_response)
        if error_msg:
            store.pusher_trigger(pusher_event, {
                'success': False,
                'error': error_msg,
                'product': product.guid
            })
            return

        # Fetch SureDone updates and update the DB
        updated_product = ebay_utils.get_ebay_product_details(parent_guid, smart_board_sync=True)

        # If the SureDone returns no data, then the product did not get imported
        if not updated_product or not isinstance(updated_product, EbayProduct):
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


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def products_supplier_sync(self, store_id, user_id, products, sync_price, price_markup, compare_markup, sync_inventory, cache_key):
    store = EbayStore.objects.get(id=store_id)
    user = User.objects.get(id=user_id)
    products = EbayProduct.objects.filter(guid__in=products, user=store.user, store=store, source_id__gt=0)
    total_count = 0
    for product in products:
        if product.have_supplier() and (product.default_supplier.is_aliexpress or product.default_supplier.is_ebay):
            total_count += 1

    push_data = {
        'task': self.request.id,
        'count': total_count,
        'success': 0,
        'fail': 0,
    }
    store.pusher_trigger('products-supplier-sync', push_data)

    for product in products:
        if not product.have_supplier() or not (product.default_supplier.is_aliexpress or product.default_supplier.is_ebay):
            continue

        supplier = product.default_supplier
        push_data['id'] = product.id
        push_data['title'] = product.title
        push_data['ebay_link'] = product.ebay_url
        push_data['supplier_link'] = supplier.product_url
        push_data['status'] = 'ok'
        push_data['error'] = None

        try:
            # Fetch supplier variants
            attempts = 3
            while attempts:
                supplier_variants = get_supplier_variants(supplier.supplier_type(), supplier.get_source_id())
                attempts -= 1
                if len(supplier_variants) > 0:
                    break

            supplier_prices = [v.get('price') for v in supplier_variants if v.get('price')]
            supplier_min_price = min(supplier_prices)
            supplier_max_price = max(supplier_prices)
        except Exception:
            push_data['status'] = 'fail'
            push_data['error'] = 'Failed to load supplier data'
            push_data['fail'] += 1
            store.pusher_trigger('products-supplier-sync', push_data)
            continue

        try:
            # Fetch ebay variants
            variants = product.retrieve_variants()
            variants = [variant.__dict__ for variant in variants]
        except Exception:
            push_data['status'] = 'fail'
            push_data['error'] = 'Failed to load ebay data'
            push_data['fail'] += 1
            store.pusher_trigger('products-supplier-sync', push_data)
            continue

        try:
            # Check if there's only one price
            # 'price' key exception is thrown if there is no variant
            if len(variants) > 1:
                same_price = (len(set([v.get('price') for v in variants if v.get('price')])) == 1
                              or supplier_min_price == supplier_max_price)
            else:
                same_price = (len(variants) == 1
                              or len(supplier_variants) == 1)
            # New Data
            updated = False
            mapped_variants = {}
            unmapped_variants = []

            if sync_price and same_price:
                # Use one price for all variants
                for i, variant in enumerate(variants):
                    variant['price'] = round(supplier_max_price * (100 + price_markup) / 100.0, 2)
                    variant['compareatprice'] = round(variant.get('price') * (100 + compare_markup) / 100.0, 2)
                    updated = True

            if (sync_price and not same_price) or sync_inventory:
                indexes = []
                for i, variant in enumerate(supplier_variants):
                    sku = variant.get('sku')
                    if not sku:
                        if len(variants) == 1 and len(supplier_variants) == 1:
                            idx = 0
                        else:
                            continue
                    else:
                        idx = variant_index_from_supplier_sku(product, sku, variants)
                        if idx is None and len(variants) > 1:
                            for j, v in enumerate(variants):
                                if j not in indexes and variant.get('sku_short') == v.get('supplier_sku') and v.get('supplier_sku'):
                                    idx = j
                                    indexes.append(j)
                                    break
                    mapped_variants[str(variants[idx].get('id'))] = True

                    # Sync inventory
                    if sync_inventory:
                        variants[idx]['stock'] = variant.get('availabe_qty')

                    # Sync price
                    if sync_price and not same_price:
                        variants[idx]['price'] = round(variant.get('price') * (100 + price_markup) / 100.0, 2)
                        variants[idx]['compareatprice'] = round(variants[idx].get('price') * (100 + compare_markup) / 100.0, 2)
                        updated = True

            # check unmapped variants
            for variant in variants:
                if not mapped_variants.get(str(variant.get('id')), False):
                    unmapped_variants.append(variant.get('variant_title'))

            # prepare synced data for an update on SureDone
            updated_product_data = {}
            for i, variant in enumerate(variants):
                if variant.get('parent_product_id') == variant.get('guid') and variant.get('guid'):
                    index_of_parent_variant = i

                variants[i] = {
                    'guid': variant.get('guid'),
                    'stock': variant.get('stock'),
                    'price': variant.get('price'),
                    'compareatprice': variant.get('compareatprice')
                }
            updated_product_data = variants[index_of_parent_variant]
            updated_product_data['variants'] = variants

            if updated:
                ebay_utils = EbayUtils(user)
                try:
                    ebay_utils.update_product_details(
                        updated_product_data=updated_product_data,
                        store_type=store.store_type,
                        store_instance_id=store.store_instance_id
                    )
                    ebay_utils.get_ebay_product_details(parent_guid=updated_product_data['guid'])
                except Exception:
                    capture_exception()
                    push_data['status'] = 'fail'
                    push_data['error'] = 'Failed to update data on Dropified'
                    push_data['fail'] += 1

            if len(unmapped_variants) > 0:
                push_data['error'] = 'Warning - Unmapped: {}'.format(','.join(unmapped_variants))
            push_data['success'] += 1
        except Exception:
            capture_exception()
            push_data['status'] = 'fail'
            push_data['error'] = 'Failed to update data'
            push_data['fail'] += 1

        store.pusher_trigger('products-supplier-sync', push_data)

    cache.delete(cache_key)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def get_import_product_options(self, store_id, user_id, page=1, page_limit=10):
    user = User.objects.get(id=user_id)
    store = EbayStore.objects.get(id=store_id)
    pusher_event = 'ebay-import-products-found'

    try:
        permissions.user_can_view(user, store)

        utils = EbayUtils(user)
        api_result = utils.get_import_products(store, user, page=page, limit=page_limit)

        response = {
            'success': True,
            'task': self.request.id,
            'current': page,
            'prev': page > 1,
            'next': api_result.get('next', False),
            'products': api_result.get('products', [])
        }

        store.pusher_trigger(pusher_event, response)

        return response

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        store.pusher_trigger(pusher_event, {
            'success': False,
            'task': self.request.id,
            'error': http_exception_response(e, json=True).get('message', 'Server Error'),
            'current': page,
            'prev': page > 1,
            'next': False
        })


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def import_product(self, store_id, user_id, product_guid, csv_position, product_variants_count,
                   supplier_url, vendor_name, vendor_url):
    user = User.objects.get(id=user_id)
    store = EbayStore.objects.get(id=store_id)
    pusher_event = 'ebay-product-import-completed'

    try:
        permissions.user_can_view(user, store)

        EbayUtils(user).import_product_from_csv(
            store=store,
            product_guid=product_guid,
            csv_position=csv_position,
            product_variants_count=product_variants_count,
            supplier_url=supplier_url,
            vendor_name=vendor_name,
            vendor_url=vendor_url)

        store.pusher_trigger(pusher_event, {
            'success': True,
            'task': self.request.id,
            'product_link': reverse('ebay:product_detail', args=[store.id, product_guid]),
        })
    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        default_error_message = 'Something went wrong. Please try submitting a new import job.'
        store.pusher_trigger(pusher_event, {
            'success': False,
            'task': self.request.id,
            'error': http_exception_response(e, json=True).get('message', default_error_message),
        })


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def sync_product_with_import_file(self, store_id, user_id, product_id, csv_position, product_variants_count):
    user = User.objects.get(id=user_id)
    store = EbayStore.objects.get(id=store_id)
    product = EbayProduct.objects.get(id=product_id)
    pusher_event = 'ebay-product-sync-completed'

    try:
        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)

        EbayUtils(user).update_product_from_import_csv(
            product=product,
            csv_position=csv_position,
            product_variants_count=product_variants_count)

        store.pusher_trigger(pusher_event, {
            'success': True,
            'task': self.request.id,
            'product': product.guid,
        })
    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        default_error_message = 'Something went wrong. Please try submitting a new import job.'
        store.pusher_trigger(pusher_event, {
            'success': False,
            'task': self.request.id,
            'error': http_exception_response(e, json=True).get('message', default_error_message),
            'product': product.guid,
        })


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def connect_product_to_ebay(self, user_id, store_id, product_id, source_id, ebay_relist_id):
    user = User.objects.get(id=user_id)
    store = EbayStore.objects.get(id=store_id)
    product = EbayProduct.objects.get(id=product_id)

    pusher_event = 'product-connected'

    try:
        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)

        resp = EbayUtils(user).set_product_ebay_id(store, product, safe_int(source_id), safe_int(ebay_relist_id))

        if resp and resp.get('result') == 'success':
            product.source_id = source_id
            product.store = store
            product.save()
            product.product_variants.all().update(source_id=source_id)
            store.pusher_trigger(pusher_event, {
                'success': True,
                'task': self.request.id,
                'product': product.id,
            })
        else:
            store.pusher_trigger(pusher_event, {
                'success': False,
                'task': self.request.id,
                'error': 'Something went wrong. Please try again',
                'product': product.id,
            })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))
        store.pusher_trigger(pusher_event, {
            'success': False,
            'task': self.request.id,
            'error': http_exception_response(e, json=True).get('message', 'Server Error'),
            'product': product.id,
        })


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def disconnect_product_from_ebay(self, user_id, store_id, product_id):
    user = User.objects.get(id=user_id)
    store = EbayStore.objects.get(id=store_id)
    product = EbayProduct.objects.get(id=product_id)

    pusher_event = 'product-disconnected'

    try:
        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)
        resp = EbayUtils(user).set_product_ebay_id(product.store, product, 0, 0)

        if resp and resp.get('result') == 'success':
            product.source_id = 0
            product.save()
            product.product_variants.all().update(source_id=0)
            store.pusher_trigger(pusher_event, {
                'success': True,
                'task': self.request.id,
                'product': product.id,
            })
        else:
            store.pusher_trigger(pusher_event, {
                'success': False,
                'task': self.request.id,
                'error': resp.get('message', 'Something went wrong.'),
                'product': product.id,
            })
    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))
        store.pusher_trigger(pusher_event, {
            'success': False,
            'task': self.request.id,
            'error': http_exception_response(e, json=True).get('message', 'Server Error'),
            'product': product.id,
        })
