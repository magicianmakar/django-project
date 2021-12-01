import simplejson as json
import requests
import re
import arrow
from tempfile import mktemp
from zipfile import ZipFile

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.cache import cache
from django.urls import reverse
from django.utils.text import slugify
from django.conf import settings
from django.template.defaultfilters import truncatewords
from django.db import IntegrityError

from lib.exceptions import capture_exception, capture_message

from app.celery_base import celery_app, CaptureFailure, retry_countdown
from shopified_core import permissions
from shopified_core.utils import (
    get_domain,
    http_exception_response,
    http_excption_status_code,
    get_fileext_from_url,
    safe_str
)
from .models import WooStore, WooProduct, WooSupplier
from .utils import (
    format_woo_errors,
    get_image_id_by_hash,
    get_product_attributes_dict,
    add_product_images_to_api_data,
    add_product_attributes_to_api_data,
    add_store_tags_to_api_data,
    update_product_api_data,
    update_variants_api_data,
    sync_variants_api_data,
    update_product_images_api_data,
    create_variants_api_data,
    get_latest_order_note,
    get_product_data,
    replace_problematic_images,
    WooOrderUpdater,
    WooListQuery,
    find_missing_orders,
    update_woo_store_order,
    get_woo_order,
)

from product_alerts.utils import (
    get_supplier_variants,
    variant_index_from_supplier_sku,
)


WOOCOMMERCE_API_TIMEOUT = 120


@celery_app.task(base=CaptureFailure)
def product_save(req_data, user_id):
    store = req_data.get('store')
    data = req_data['data']

    user = User.objects.get(id=user_id)

    # raven_client.extra_context({'store': store, 'product': req_data.get('product'), 'from_extension': ('access_token' in req_data)})

    if store:
        try:
            store = WooStore.objects.get(id=store)
            permissions.user_can_view(user, store)

        except (WooStore.DoesNotExist, ValueError):
            capture_exception()

            return {
                'error': 'Selected store (%s) not found' % (store)
            }
        except PermissionDenied as e:
            return {
                'error': "Store: {}".format(str(e))
            }
    else:
        store = user.profile.get_woo_stores().first()

    original_url = json.loads(data).get('original_url')
    if not original_url:
        original_url = req_data.get('original_url')

    try:
        import_store = get_domain(original_url)
    except:
        capture_exception(extra={'original_url': original_url})

        return {
            'error': 'Original URL is not set.'
        }

    if not import_store or not user.can('%s_import.use' % import_store):
        if not import_store:
            import_store = 'N/A'

        if not user.can('import_from_any.use'):
            return {
                'error': 'Importing from this store ({}) is not included in your current plan.'.format(import_store)
            }

    if req_data.get('product'):
        # Saved product update
        try:
            product = WooProduct.objects.get(id=req_data['product'])
            permissions.user_can_edit(user, product)

        except WooProduct.DoesNotExist:
            capture_exception()
            return {
                'error': "Product {} does not exist".format(req_data['product'])
            }

        except PermissionDenied as e:
            capture_exception()
            return {
                'error': "Product: {}".format(str(e))
            }

        product.update_data(data)
        product.store = store

        product.save()

    else:  # New product to save

        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)
        if not can_add:
            return {
                'error': "Woohoo! 🎉. You are growing and you've hit your account limit for products. "
                         "Upgrade your plan to keep importing new products"
            }

        try:
            data = replace_problematic_images(data)
            product = WooProduct(store=store, user=user.models_user)
            product.update_data(data)
            user_supplement_id = json.loads(data).get('user_supplement_id')
            product.user_supplement_id = user_supplement_id
            permissions.user_can_add(user, product)
            product.save()

            store_info = json.loads(data).get('store')

            supplier = WooSupplier.objects.create(
                store=store,
                product=product,
                product_url=safe_str(original_url)[:512],
                supplier_name=store_info.get('name') if store_info else '',
                supplier_url=store_info.get('url') if store_info else '',
                is_default=True
            )

            product.set_default_supplier(supplier, commit=True)

        except PermissionDenied as e:
            capture_exception()
            return {
                'error': "Add Product: {}".format(str(e))
            }

    return {
        'product': {
            'url': reverse('woo:product_detail', kwargs={'pk': product.id}),
            'id': product.id,
        }
    }


@celery_app.task(base=CaptureFailure)
def product_export(store_id, product_id, user_id, publish=None):
    try:
        user = User.objects.get(id=user_id)
        store = WooStore.objects.get(id=store_id)
        product = WooProduct.objects.get(id=product_id)

        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)

        product.store = store
        # Avoid .save() to allow "Importing..." title to change after product is imported
        WooProduct.objects.filter(id=product_id).update(store_id=store_id)

        saved_data = product.parsed
        saved_data['published'] = saved_data['published'] if publish is None else publish
        api_data = update_product_api_data({}, saved_data, store)
        api_data = add_product_images_to_api_data(api_data, saved_data, user_id=user_id)
        attributes = get_product_attributes_dict(store)
        api_data = add_product_attributes_to_api_data(api_data, saved_data, attributes)
        api_data = add_store_tags_to_api_data(api_data, store, saved_data.get('tags', []))

        product_data = None
        r = store.get_wcapi(timeout=WOOCOMMERCE_API_TIMEOUT).post('products', api_data)
        if not r.ok:
            is_image_error = False
            try:
                error_result = r.json()
                if error_result.get('code') == 'woocommerce_product_image_upload_error':
                    is_image_error = True
            except:
                pass

            # Retry using dropified helper to fetch image
            if is_image_error:
                api_data = add_product_images_to_api_data(api_data, saved_data, user_id=user_id, from_helper=True)
                r = store.get_wcapi(timeout=WOOCOMMERCE_API_TIMEOUT).post('products', api_data)

                r.raise_for_status()
                if r.ok:
                    product_data = r.json()
                    product.source_id = product_data['id']
            else:
                product_data = None

                if '/products/' in r.url:
                    product_id = re.findall(r'/products/([0-9]+)', r.url)
                    if len(product_id) == 1:
                        product.source_id = int(product_id[0])

                if not product.source_id:
                    r.raise_for_status()
        else:
            product_data = r.json()
            product.source_id = product_data['id']

        product.save()

        if product_data and saved_data.get('variants', []):
            image_id_by_hash = get_image_id_by_hash(api_data, product_data)
            variant_list = create_variants_api_data(saved_data, image_id_by_hash, attributes)
            path = 'products/{}/variations/batch'.format(product.source_id)
            r = store.get_wcapi(timeout=WOOCOMMERCE_API_TIMEOUT).post(path, {'create': variant_list})
            r.raise_for_status()
            variants = r.json()['create']

            if product.default_supplier:
                variants_mapping = {}
                for variant in variants:
                    variant_id = variant.get('id')
                    if variant_id not in variants_mapping:
                        variants_mapping[variant_id] = []

                    variant_titles = [{'title': t.get('option')} for t in variant.get('attributes')]
                    variants_mapping[variant_id].extend(variant_titles)

                for variant_id in variants_mapping:
                    variants_mapping[variant_id] = json.dumps(variants_mapping[variant_id])

                if variants_mapping:
                    product.default_supplier.variants_map = json.dumps(variants_mapping)
                else:
                    product.default_supplier.variants_map = None

                product.default_supplier.save()

        # Initial Products Inventory Sync
        if user.models_user.get_config('initial_inventory_sync', True):
            sync_woo_product_quantities.apply_async(args=[product.id], countdown=0)

        store.pusher_trigger('product-export', {
            'success': True,
            'product': product.id,
            'product_url': reverse('woo:product_detail', kwargs={'pk': product.id}),
            'woocommerce_url': product.woocommerce_url
        })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        store.pusher_trigger('product-export', {
            'success': False,
            'error': format_woo_errors(e),
            'product': product.id,
            'product_url': reverse('woo:product_detail', kwargs={'pk': product.id}),
        })


@celery_app.task(base=CaptureFailure)
def product_update(product_id, data):
    try:
        product = WooProduct.objects.get(id=product_id)
        store = product.store
        api_data = product.retrieve()
        api_data = update_product_api_data(api_data, data, store)
        api_data = add_store_tags_to_api_data(api_data, store, data.get('tags', []))
        api_data = update_product_images_api_data(api_data, data)

        variants_data = data.get('variants', [])
        if variants_data:
            api_data['type'] = 'variable'

        r = store.get_wcapi(timeout=WOOCOMMERCE_API_TIMEOUT).put('products/{}'.format(product.source_id), api_data)
        r.raise_for_status()

        product.update_data({'type': data.get('type', '')})
        product.source_id = r.json()['id']
        product.save()

        if variants_data:
            variants = update_variants_api_data(variants_data)
            path = 'products/%s/variations/batch' % product.source_id
            r = store.get_wcapi(timeout=WOOCOMMERCE_API_TIMEOUT).post(path, {'update': variants})
            r.raise_for_status()

        store.pusher_trigger('product-update', {
            'success': True,
            'product': product.id,
            'product_url': reverse('woo:product_detail', kwargs={'pk': product.id})
        })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        store.pusher_trigger('product-update', {
            'success': False,
            'error': format_woo_errors(e),
            'product': product.id,
            'product_url': reverse('woo:product_detail', kwargs={'pk': product.id})
        })


@celery_app.task(bind=True, base=CaptureFailure)
def create_image_zip(self, images, product_id):
    from leadgalaxy.utils import aws_s3_upload

    try:
        product = WooProduct.objects.get(pk=product_id)
        filename = mktemp(suffix='.zip', prefix='{}-'.format(product_id))

        with ZipFile(filename, 'w') as images_zip:
            for i, img_url in enumerate(images):
                image_name = 'image-{}.{}'.format(i + 1, get_fileext_from_url(img_url, fallback='jpg'))
                images_zip.writestr(image_name, requests.get(img_url, verify=not settings.DEBUG).content)

        product_filename = 'product-images.zip'
        if slugify(product.title):
            product_filename = f'{slugify(product.title)[:100]}-images.zip'

        s3_path = f'product-downloads/{product.id}/{product_filename}'
        url = aws_s3_upload(s3_path, input_filename=filename, mimetype='application/zip')

        product.store.pusher_trigger('images-download', {
            'success': True,
            'product': product_id,
            'url': url
        })
    except Exception:
        capture_exception()

        product.store.pusher_trigger('images-download', {
            'success': False,
            'product': product_id,
        })


@celery_app.task(base=CaptureFailure)
def get_latest_order_note_task(store_id, order_ids):
    store = WooStore.objects.get(pk=store_id)
    have_error = False

    for order_id in order_ids:
        data = {'order_id': order_id, 'success': False}

        if not have_error:
            try:
                data['success'] = True
                data['note'] = get_latest_order_note(store, order_id)

            except Exception as e:
                have_error = True
                if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
                    capture_exception(extra=http_exception_response(e))

        store.pusher_trigger('get-order-note', data)


@celery_app.task(base=CaptureFailure, bind=True)
def order_save_changes(self, data):
    order_id = None
    try:
        updater = WooOrderUpdater()
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
            countdown = retry_countdown('retry_ordered_tags_{}'.format(order_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def sync_woo_product_quantities(self, product_id):
    try:
        product = WooProduct.objects.get(pk=product_id)
        product_data = product.retrieve()

        if not product.default_supplier:
            return

        variant_quantities = get_supplier_variants(product.default_supplier.supplier_type(), product.default_supplier.get_source_id())
        if product_data and variant_quantities:
            for variant in variant_quantities:
                sku = variant.get('sku')
                variant_id = 0
                idx = variant_index_from_supplier_sku(product, sku, product_data['variants'])
                if idx is not None:
                    variant_id = product_data['variants'][idx]['id']
                if variant_id > 0:
                    product_data['variants'][idx]['stock_quantity'] = variant['availabe_qty']
                    product_data['variants'][idx]['manage_stock'] = True
                elif len(product_data.get('variants', [])) == 0 or variant_id < 0:
                    product_data['stock_quantity'] = variant['availabe_qty']
                    product_data['manage_stock'] = True

            update_endpoint = 'products/{}'.format(product.source_id)
            variants_update_endpoint = 'products/{}/variations/batch'.format(product.source_id)
            r = product.store.wcapi.put(update_endpoint, product_data)
            r.raise_for_status()
            r = product.store.wcapi.put(variants_update_endpoint, {
                'update': product_data['variants'],
            })
            r.raise_for_status()

        cache.delete('product_inventory_sync_woo_{}_{}'.format(product.id, product.default_supplier.id))

    except WooProduct.DoesNotExist:
        pass
    except Exception as e:
        capture_exception()

        if not self.request.called_directly:
            countdown = retry_countdown('retry_sync_woo_{}'.format(product_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def products_supplier_sync(self, store_id, products, sync_price, price_markup, compare_markup, sync_inventory, cache_key):
    store = WooStore.objects.get(id=store_id)
    products = WooProduct.objects.filter(id__in=products, user=store.user, store=store, source_id__gt=0)
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

        woocommerce_id = product.source_id
        supplier = product.default_supplier
        push_data['id'] = product.id
        push_data['title'] = product.title
        push_data['woo_link'] = product.woocommerce_url
        push_data['supplier_link'] = supplier.product_url
        push_data['status'] = 'ok'
        push_data['error'] = None

        try:
            # Fetch supplier variants
            supplier_variants = get_supplier_variants(supplier.supplier_type(), supplier.get_source_id())

            supplier_prices = [v['price'] for v in supplier_variants]
            supplier_min_price = min(supplier_prices)
            supplier_max_price = max(supplier_prices)
        except Exception:
            push_data['status'] = 'fail'
            push_data['error'] = 'Failed to load supplier data'
            push_data['fail'] += 1
            store.pusher_trigger('products-supplier-sync', push_data)
            continue

        try:
            # Fetch woocommerce variants
            product_data = get_product_data(store, [woocommerce_id])[woocommerce_id]
            variants = product.retrieve_variants()
        except Exception:
            push_data['status'] = 'fail'
            push_data['error'] = 'Failed to load woocommerce data'
            push_data['fail'] += 1
            store.pusher_trigger('products-supplier-sync', push_data)
            continue

        try:
            # Check if there's only one price
            # 'price' key exception is thrown if there is no variant
            if len(variants) > 1:
                same_price = (len(set([v['price'] for v in variants])) == 1
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
                    variant['compare_at_price'] = round(supplier_variants[i]['price'] * (100 + compare_markup) / 100.0, 2)
                    updated = True

            if (sync_price and not same_price) or sync_inventory:
                for i, variant in enumerate(supplier_variants):
                    sku = variant.get('sku')
                    if not sku:
                        if len(variants) == 1 and len(supplier_variants) == 1:
                            idx = 0
                        else:
                            continue
                    else:
                        idx = variant_index_from_supplier_sku(product, sku, variants)

                        variant_id = 0
                        if idx is not None:
                            variant_id = variants[idx]['id']
                        if variant_id > 0:
                            variants[idx]['stock_quantity'] = variant['availabe_qty']
                            variants[idx]['manage_stock'] = True
                        elif len(product_data.get('variants', [])) == 0 or variant_id < 0:
                            product_data['stock_quantity'] = variant['availabe_qty']
                            product_data['manage_stock'] = True
                        if idx is None:
                            if len(variants) == 1 and len(supplier_variants) == 1:
                                idx = 0
                            else:
                                continue

                    mapped_variants[str(variants[idx]['id'])] = True
                    # Sync price
                    if sync_price and not same_price:
                        variant['price'] = round(supplier_variants[idx]['price'] * (100 + price_markup) / 100.0, 2)
                        variant['compare_at_price'] = round(supplier_variants[idx]['price'] * (100 + compare_markup) / 100.0, 2)
                        updated = True

                # check unmapped variants
                if len(variants) == 1 and len(supplier_variants) == 1 and variants[idx]['id'] < 0:
                    product_data['stock_quantity'] = supplier_variants[0]["availabe_qty"]
                    product_data['manage_stock'] = True
                    product_data['regular_price'] = str(round(supplier_variants[0]['price'] * (100 + price_markup) / 100.0, 2))
                    updated = True
                else:
                    variants = sync_variants_api_data(variants, sync_inventory)
                    for variant in variants:
                        if not mapped_variants.get(str(variant['id']), False):
                            unmapped_variants.append(variant['title'])

            if updated or sync_inventory:
                update_endpoint = 'products/{}'.format(product.source_id)
                variants_update_endpoint = 'products/{}/variations/batch'.format(product.source_id)
                r = product.store.wcapi.put(update_endpoint, product_data)
                r.raise_for_status()
                r = product.store.get_wcapi(timeout=WOOCOMMERCE_API_TIMEOUT).post(variants_update_endpoint, {
                    'update': variants,
                })
                r.raise_for_status()

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
def sync_woo_orders(self, store_id):
    try:
        start_time = arrow.now()
        store = WooStore.objects.get(id=store_id)
        max_days_sync = 30
        saved_count = store.count_saved_orders(days=max_days_sync)
        woo_count = WooListQuery(store, 'orders').count()
        need_import = woo_count - saved_count

        if need_import > 0:
            capture_message('Sync Store Orders', level='info', extra={
                'store': store.title, 'es': False, 'missing': need_import
            }, tags={'store': store.title, 'es': False})

            imported = 0
            page = 1

            while page:
                if imported >= need_import:
                    break
                after = arrow.utcnow().replace(days=-abs(max_days_sync)).isoformat()
                params = {'page': page, 'per_page': 100, 'after': after}
                r = store.wcapi.get('orders', params=params)
                r.raise_for_status()
                orders = r.json()

                if not orders:
                    break

                missing_orders = find_missing_orders(store, orders)
                for missing_order in missing_orders:
                    update_woo_store_order(store, missing_order)
                    imported += 1

                has_next = 'rel="next"' in r.headers.get('link', '')
                page = page + 1 if has_next else 0

            took = (arrow.now() - start_time).seconds
            print('Sync Need: {}, Total: {}, Imported: {}, Store: {}, Took: {}s'.format(
                need_import, woo_count, imported, store.title, took))

    except Exception:
        capture_exception()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def update_woo_order(self, store_id, order_id, woo_order=None, from_webhook=True):
    store = None
    try:
        store = WooStore.objects.get(id=store_id)

        if not store.is_active:
            return

        # if not store.is_active or store.user.get_config('_disable_update_woo_order'):
        #     return

        if woo_order is None:
            woo_order = cache.get('woo_webhook_order_{}_{}'.format(store_id, order_id))

        if woo_order is None:
            woo_order = get_woo_order(store, order_id)

        with cache.lock('woo_order_lock_{}_{}'.format(store_id, order_id), timeout=10):
            try:
                update_woo_store_order(store, woo_order)
            except IntegrityError as e:
                raise self.retry(exc=e, countdown=30, max_retries=3)

        # active_order_key = 'woo_active_order_{}'.format(woo_order['id'])

    except AssertionError:
        capture_message('Store is being imported', extra={'store': store})

    except WooStore.DoesNotExist:
        capture_exception()

    except Exception as e:
        if http_excption_status_code(e) in [401, 402, 403, 404]:
            return

        if http_excption_status_code(e) != 429:
            capture_exception(level='warning', extra={
                'Store': store_id,
                'Order': order_id,
                'from_webhook': from_webhook,
                'Retries': self.request.retries
            }, tags={
                'store': store.id if store else 'N/A',
                'webhook': from_webhook,
            })

        # if not self.request.called_directly:
        #     countdown = retry_countdown('retry_order_{}'.format(order_id), self.request.retries)
        #     raise self.retry(exc=e, countdown=countdown, max_retries=3)
