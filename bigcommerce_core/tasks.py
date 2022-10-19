import simplejson as json
import requests
import re
from tempfile import mktemp
from zipfile import ZipFile

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.cache import cache
from django.urls import reverse
from django.utils.text import slugify
from django.conf import settings
from django.template.defaultfilters import truncatewords

from lib.exceptions import capture_exception

from app.celery_base import celery_app, CaptureFailure, retry_countdown
from multichannel_products_core.utils import rewrite_master_variants_map
from shopified_core.utils import (
    get_domain,
    http_exception_response,
    http_excption_status_code,
    get_fileext_from_url,
    safe_str
)
from shopified_core import permissions

from .models import BigCommerceStore, BigCommerceProduct, BigCommerceSupplier
from .utils import (
    BigCommerceOrderUpdater,
    format_bigcommerce_errors,
    get_image_url_by_hash,
    add_product_images_to_api_data,
    update_product_api_data,
    update_variants_api_data,
    update_product_images_api_data,
    create_variants_api_data,
    get_latest_order_note,
    find_or_create_category,
    get_product_data,
    get_deleted_product_images,
)

from product_alerts.utils import (
    get_supplier_variants,
    variant_index_from_supplier_sku,
)


@celery_app.task(base=CaptureFailure)
def product_save(req_data, user_id):
    store = req_data.get('store')
    data = req_data['data']
    user = User.objects.get(id=user_id)

    # raven_client.extra_context({'store': store, 'product': req_data.get('product'), 'from_extension': ('access_token' in req_data)})

    if store:
        try:
            store = BigCommerceStore.objects.get(id=store)
            permissions.user_can_view(user, store)

        except (BigCommerceStore.DoesNotExist, ValueError):
            capture_exception()

            return {
                'error': 'Selected store (%s) not found' % (store)
            }
        except PermissionDenied as e:
            return {
                'error': "Store: {}".format(str(e))
            }
    else:
        store = user.profile.get_bigcommerce_stores().first()

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
            product = BigCommerceProduct.objects.get(id=req_data['product'])
            permissions.user_can_edit(user, product)

        except BigCommerceProduct.DoesNotExist:
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

        rewrite_master_variants_map(product)
        product.save()

    else:  # New product to save

        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)
        if not can_add:
            return {
                'error': "Woohoo! 🎉. You are growing and you've hit your account limit for products. "
                         "Upgrade your plan to keep importing new products"
            }

        try:
            product = BigCommerceProduct(store=store, user=user.models_user)
            product.update_data(data)
            user_supplement_id = json.loads(data).get('user_supplement_id')
            product.user_supplement_id = user_supplement_id

            permissions.user_can_add(user, product)
            product.save()

            store_info = json.loads(data).get('store')

            supplier = BigCommerceSupplier.objects.create(
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
            'url': reverse('bigcommerce:product_detail', kwargs={'pk': product.id}),
            'id': product.id,
        }
    }


@celery_app.task(base=CaptureFailure)
def product_export(store_id, product_id, user_id, publish=None):
    try:
        user = User.objects.get(id=user_id)
        store = BigCommerceStore.objects.get(id=store_id)
        product = BigCommerceProduct.objects.get(id=product_id)

        if product.source_id and product.store.id == store.id:
            raise ValueError('Product already connected to BigCommerce store.')

        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)

        product.store = store
        # Avoid .save() to allow "Importing..." title to change after product is imported
        BigCommerceProduct.objects.filter(id=product_id).update(store_id=store_id)

        saved_data = product.parsed
        saved_data['published'] = saved_data['published'] if publish is None else publish

        api_data = update_product_api_data({}, saved_data)

        api_data = add_product_images_to_api_data(api_data, saved_data)
        if saved_data.get('variants', []):
            image_url_by_hash = get_image_url_by_hash(saved_data)
            api_data['variants'] = create_variants_api_data(product_id, saved_data, image_url_by_hash)

        default_category = find_or_create_category(store)
        api_data['categories'] = [default_category['id']]

        r = store.request.post(
            url=store.get_api_url('v3/catalog/products'),
            json=api_data
        )
        if not r.ok:
            is_image_error = False
            try:
                error_result = r.json()
                if error_result.get('errors', {}).get('images', None) is not None:
                    is_image_error = True
            except:
                pass

            # Retry using dropified helper to fetch image
            if is_image_error:
                api_data = add_product_images_to_api_data(api_data, saved_data, from_helper=True)
                r = store.request.post(
                    url=store.get_api_url('v3/catalog/products'),
                    json=api_data
                )

                if r.ok:
                    product_data = r.json()['data']
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
            product_data = r.json()['data']
            product.source_id = product_data['id']

        product.save()

        if product_data and product_data.get('variants', []):
            variants = product_data.get('variants', [])

            if product.default_supplier:
                variants_mapping = {}
                for variant in variants:
                    variant_id = variant.get('id')
                    if variant_id not in variants_mapping:
                        variants_mapping[variant_id] = []

                    variant_titles = [{'title': t.get('label')} for t in variant.get('option_values')]
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
            sync_bigcommerce_product_quantities.apply_async(args=[product.id], countdown=0)

        store.pusher_trigger('product-export', {
            'success': True,
            'product': product.id,
            'product_url': reverse('bigcommerce:product_detail', kwargs={'pk': product.id}),
            'bigcommerce_url': product.bigcommerce_url
        })

    except ValueError as e:
        store.pusher_trigger('product-export', {
            'success': False,
            'error': str(e),
            'product': product.id,
            'product_url': reverse('bigcommerce:product_detail', kwargs={'pk': product.id}),
        })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        store.pusher_trigger('product-export', {
            'success': False,
            'error': format_bigcommerce_errors(e),
            'product': product.id,
            'product_url': reverse('bigcommerce:product_detail', kwargs={'pk': product.id}),
        })


@celery_app.task(base=CaptureFailure)
def product_update(product_id, data):
    try:
        product = BigCommerceProduct.objects.get(id=product_id)
        store = product.store
        api_data = product.retrieve()
        deleted_images = get_deleted_product_images(api_data, data)
        api_data = update_product_api_data(api_data, data)
        api_data = update_product_images_api_data(api_data, data)

        # filter out already existing variants
        variants = [variant for variant in data.get('variants', []) if variant.get('id')]
        api_data['variants'] = update_variants_api_data(api_data.get('variants', []), variants)

        r = store.request.put(
            url=store.get_api_url('v3/catalog/products/%s' % product.source_id),
            json=api_data
        )
        r.raise_for_status()
        product.source_id = r.json()['data']['id']

        # filter out new variants
        new_variants = [variant for variant in data.get('variants', []) if not variant.get('id')]

        # create new variant options/option values if were added
        new_options = data.get('options')
        for option in new_options:
            if not option.get('option_id'):
                r = store.request.post(
                    url=store.get_api_url(
                        f'v3/catalog/products/{product.source_id}/options'),
                    json={
                        'display_name': option.get('display_name'),
                        'type': 'rectangles',
                        'option_values': [{
                            "label": option.get('label'),
                            "sort_order": 0,
                        }],
                        'sort_order': 0,
                    }
                )
                r.raise_for_status()
                api_data['options'].append(r.json()['data'])
                option['option_id'] = r.json()['data']['id']
                option['id'] = r.json()['data']['option_values'][0]['id']
            else:
                r = store.request.post(
                    url=store.get_api_url(
                        f'v3/catalog/products/{product.source_id}/options/{option.get("option_id")}/values'),
                    json={
                        'label': option.get('label'),
                        'sort_order': 0,
                    }
                )
                r.raise_for_status()
                option['id'] = r.json()['data']['id']

            for item in api_data.get('options', []):
                if item['id'] == option.get('option_id'):
                    value = {
                        'id': option['id'],
                        'label': option['label'],
                        'sort_order': 0,
                        'value_data': None,
                        'is_default': False
                    }
                    if item.get('option_values'):
                        item.get('option_values').append(value)
                    else:
                        item['option_values'] = [value]

        # prepare and create new variants in store
        for variant in new_variants:
            for idx, option_value in enumerate(variant.get('option_values', [])):
                for option in api_data.get('options', []):
                    item = next((value for value in option.get('option_values', [])
                                 if value.get('label') == option_value.get('label')
                                 and option.get('display_name') == option_value.get('option_display_name')), None)
                    if item:
                        variant['option_values'][idx]['id'] = item.get('id')
                        variant['option_values'][idx]['option_id'] = option.get('id')
                        break
            if variant.get('image'):
                variant['image_url'] = variant.get('image')
            elif data.get('images'):
                variant['image_url'] = data['images'][0]

            if variant.get('compare_at_price'):
                variant['price'] = str(variant['compare_at_price'])
                variant['sale_price'] = str(variant['price'])
            else:
                variant['price'] = str(variant['price'])

            r = store.request.post(
                url=store.get_api_url(f'v3/catalog/products/{product.source_id}/variants'),
                json=variant
            )
            r.raise_for_status()

        for image_id in deleted_images:
            r = store.request.delete(
                url=store.get_api_url(f'v3/catalog/products/{product.source_id}/images/{image_id}'))
            r.raise_for_status()

        product.save()
        store.pusher_trigger('product-update', {
            'success': True,
            'product': product.id,
            'product_url': reverse('bigcommerce:product_detail', kwargs={'pk': product.id})
        })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        store.pusher_trigger('product-update', {
            'success': False,
            'error': format_bigcommerce_errors(e),
            'product': product.id,
            'product_url': reverse('bigcommerce:product_detail', kwargs={'pk': product.id})
        })


@celery_app.task(bind=True, base=CaptureFailure)
def create_image_zip(self, images, product_id):
    from leadgalaxy.utils import aws_s3_upload

    try:
        product = BigCommerceProduct.objects.get(pk=product_id)
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
    store = BigCommerceStore.objects.get(pk=store_id)
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


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def sync_bigcommerce_product_quantities(self, product_id):
    try:
        product = BigCommerceProduct.objects.get(pk=product_id)
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
                    product_data['variants'][idx]['inventory_level'] = variant['availabe_qty']
                    if len(product_data['variants'][idx]['option_values']):  # BigCommerce product will always have a variant
                        product_data['inventory_tracking'] = 'variant'
                    else:
                        product_data['inventory_tracking'] = 'product'
                elif len(product_data.get('variants', [])) == 0 or variant_id < 0 or product_data['base_variant_id'] == variant_id:
                    product_data['inventory_level'] = variant['availabe_qty']
                    product_data['inventory_tracking'] = 'product'

            r = product.store.request.put(
                url=product.store.get_api_url('v3/catalog/products/%s' % product.source_id),
                json=product_data
            )
            r.raise_for_status()

        cache.delete('product_inventory_sync_bigcommerce_{}_{}'.format(product.id, product.default_supplier.id))

    except BigCommerceProduct.DoesNotExist:
        pass
    except Exception as e:
        capture_exception()

        if not self.request.called_directly:
            countdown = retry_countdown('retry_sync_bigcommerce_{}'.format(product_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure, bind=True)
def order_save_changes(self, data):
    order_id = None
    try:
        updater = BigCommerceOrderUpdater()
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
        capture_exception(extra=http_exception_response(e))

        if not self.request.called_directly:
            countdown = retry_countdown('retry_ordered_tags_{}'.format(order_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def products_supplier_sync(self, store_id, products, sync_price, price_markup, compare_markup, sync_inventory, cache_key):
    store = BigCommerceStore.objects.get(id=store_id)
    products = BigCommerceProduct.objects.filter(id__in=products, user=store.user, store=store, source_id__gt=0)
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

        bigcommerce_id = product.get_bigcommerce_id()
        supplier = product.default_supplier
        push_data['id'] = product.id
        push_data['title'] = product.title
        push_data['bigcommerce_link'] = product.bigcommerce_url
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
            # Fetch bigcommerce variants
            product_data = get_product_data(store, [bigcommerce_id])[bigcommerce_id]
        except Exception:
            push_data['status'] = 'fail'
            push_data['error'] = 'Failed to load bigcommerce data'
            push_data['fail'] += 1
            store.pusher_trigger('products-supplier-sync', push_data)
            continue

        try:
            # Check if there's only one price
            seem_price = (len('variants') == 1
                          or len(set([v['price'] for v in product_data['variants']])) == 1
                          or len(supplier_variants) == 1
                          or supplier_min_price == supplier_max_price)
            # New Data
            updated = False
            mapped_variants = {}
            unmapped_variants = []

            if sync_price and seem_price:
                # Use one price for all variants
                for i, variant in enumerate(product_data['variants']):
                    product_data['variants'][i]['price'] = round(supplier_max_price * (100 + price_markup) / 100.0, 2)
                    product_data['variants'][i]['compare_at_price'] = round(supplier_variants[i]['price'] * (100 + compare_markup) / 100.0, 2)
                    updated = True

            if (sync_price and not seem_price) or sync_inventory:
                for i, variant in enumerate(supplier_variants):
                    sku = variant.get('sku')
                    if not sku:
                        if len(product_data['variants']) == 1 and len(supplier_variants) == 1:
                            idx = 0
                        else:
                            continue
                    else:
                        idx = variant_index_from_supplier_sku(product, sku, product_data['variants'])

                    variant_id = 0
                    if idx is not None:
                        variant_id = product_data['variants'][idx]['id']
                    if variant_id > 0:
                        product_data['variants'][idx]['inventory_level'] = variant['availabe_qty']
                        if len(product_data['variants'][idx]['option_values']):  # BigCommerce product will always have a variant
                            product_data['inventory_tracking'] = 'variant'
                        else:
                            product_data['inventory_tracking'] = 'product'
                    elif len(product_data.get('variants', [])) == 0 or variant_id < 0:
                        product_data['inventory_level'] = variant['availabe_qty']
                        product_data['inventory_tracking'] = 'product'
                    if idx is None:
                        if len(product_data['variants']) == 1 and len(supplier_variants) == 1:
                            idx = 0
                        else:
                            continue

                    mapped_variants[str(product_data['variants'][idx]['id'])] = True
                    # Sync price
                    if sync_price and not seem_price:
                        product_data['variants'][i]['price'] = round(supplier_variants[idx]['price'] * (100 + price_markup) / 100.0, 2)
                        product_data['variants'][i]['compare_at_price'] = round(supplier_variants[idx]['price'] * (100 + compare_markup) / 100.0, 2)
                        updated = True

                # check unmapped variants
                temp = []
                for variant in product_data['variants']:
                    for vrnt in variant['option_values']:
                        temp.append(vrnt['label'])
                    vrnt_title = ' / '.join(temp)
                    temp = []

                    if not mapped_variants.get(str(variant['id']), False):
                        unmapped_variants.append(vrnt_title)

            if updated or sync_inventory:
                r = product.store.request.put(
                    url=product.store.get_api_url('v3/catalog/products/%s' % bigcommerce_id),
                    json=product_data
                )
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
