from json import JSONDecodeError
from requests.exceptions import HTTPError

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.template.defaultfilters import truncatewords
from django.urls import reverse
from django.utils import timezone

from app.celery_base import CaptureFailure, celery_app, retry_countdown
from lib.exceptions import capture_exception
from product_alerts.utils import get_supplier_variants, variant_index_from_supplier_sku
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
            return api_error_messages

        product.last_export_date = timezone.now()
        product.save()

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
        for variant in product_data['variants']:
            media1 = variant.pop('image')
            variant['media1'] = (media1 if variant['guid'] != variant['sku'] and media1 in media
                                 else product_data['media1'])
            for i in range(2, 11):
                if product_data.get(f'media{i}'):
                    variant[f'media{i}'] = product_data.get(f'media{i}')
            if product_data.get('mediax'):
                variant['mediax'] = product_data['mediax']

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
        updated_product = fb_utils.get_fb_product_details(
            parent_guid,
            smart_board_sync=True,
            add_model_fields={'fb_category_name': product_data.get('fb_category_name', '')}
        )

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


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def products_supplier_sync(self, store_id, user_id, products, sync_price, price_markup, compare_markup, sync_inventory, cache_key):
    store = FBStore.objects.get(id=store_id)
    user = User.objects.get(id=user_id)
    products = FBProduct.objects.filter(guid__in=products, user=store.user, store=store, source_id__gt=0)
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
        push_data['fb_link'] = product.fb_url
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
            # Fetch facebook variants
            variants = product.retrieve_variants()
            variants = [variant.__dict__ for variant in variants]
        except Exception:
            push_data['status'] = 'fail'
            push_data['error'] = 'Failed to load facebook data'
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
                            if idx is None:
                                continue
                        elif len(variants) == 1 and len(supplier_variants) == 1:
                            idx = 0

                    mapped_variants[str(variants[idx].get('id'))] = True

                    # Sync inventory
                    if sync_inventory:
                        variants[idx]['stock'] = variant.get('availabe_qty')

                    # Sync price
                    if sync_price and not same_price:
                        variants[idx]['price'] = round(variant.get('price') * (100 + price_markup) / 100.0, 2)
                        variants[idx]['compareatprice'] = round(variants[idx].get('price') * (100 + compare_markup) / 100.0, 2)
                        updated = True

                    if len(variants) == len(indexes):
                        break

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
                fb_utils = FBUtils(user)
                try:
                    fb_utils.update_product_details(
                        updated_product_data=updated_product_data,
                        store_type=store.store_type,
                        store_instance_id=store.store_instance_id
                    )
                    fb_utils.get_fb_product_details(parent_guid=updated_product_data['guid'])
                except Exception:
                    capture_exception()
                    push_data['status'] = 'fail'
                    push_data['error'] = 'Failed to update data'
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
