import simplejson as json
from tempfile import mktemp
from zipfile import ZipFile

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils.text import slugify
from django.template.defaultfilters import truncatewords
from django.core.cache import cache
import requests
from lib.exceptions import capture_exception

from app.celery_base import celery_app, CaptureFailure, retry_countdown
from shopified_core import permissions
from shopified_core.utils import (
    add_http_schema,
    all_possible_cases,
    get_domain,
    get_fileext_from_url,
    get_filename_from_url,
    get_mimetype,
    hash_url_filename,
    http_exception_response,
    http_excption_status_code,
    normalize_product_title,
    safe_float,
    safe_str
)

from churnzero_core.utils import post_churnzero_product_import, post_churnzero_product_export
from .utils import format_chq_errors, CHQOrderUpdater, get_chq_product
from .models import (
    CommerceHQStore,
    CommerceHQProduct,
    CommerceHQSupplier
)

from product_alerts.utils import (
    get_supplier_variants,
    variant_index_from_supplier_sku
)


@celery_app.task(base=CaptureFailure)
def product_save(req_data, user_id):
    store = req_data.get('store')
    data = req_data['data']
    user = User.objects.get(id=user_id)

    # raven_client.extra_context({'store': store, 'product': req_data.get('product'), 'from_extension': ('access_token' in req_data)})

    if store:
        try:
            store = CommerceHQStore.objects.get(id=store)
            permissions.user_can_view(user, store)

        except (CommerceHQStore.DoesNotExist, ValueError):
            capture_exception()

            return {
                'error': 'Selected store (%s) not found' % (store)
            }
        except PermissionDenied as e:
            return {
                'error': "Store: {}".format(str(e))
            }
    else:
        store = user.profile.get_chq_stores().first()

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
            product = CommerceHQProduct.objects.get(id=req_data['product'])
            permissions.user_can_edit(user, product)

        except CommerceHQProduct.DoesNotExist:
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
                'error': 'Your current plan allows up to %d saved product(s). Currently you have %d saved products.'
                         % (total_allowed, user_count)
            }

        try:
            product = CommerceHQProduct(store=store, user=user.models_user, notes=req_data.get('notes'))
            product.update_data(data)

            user_supplement_id = json.loads(data).get('user_supplement_id')
            product.user_supplement_id = user_supplement_id

            permissions.user_can_add(user, product)

            product.save()

            store_info = json.loads(data).get('store')
            supplier = CommerceHQSupplier.objects.create(
                store=store,
                product=product,
                product_url=safe_str(original_url)[:512],
                supplier_name=store_info.get('name') if store_info else '',
                supplier_url=store_info.get('url') if store_info else '',
                is_default=True
            )

            product.set_default_supplier(supplier, commit=True)

            post_churnzero_product_import(user, product.title, store_info.get('name', ''))

        except PermissionDenied as e:
            capture_exception()
            return {
                'error': "Add Product: {}".format(str(e))
            }

    return {
        'product': {
            'url': reverse('chq:product_detail', kwargs={'pk': product.id}),
            'id': product.id,
        }
    }


@celery_app.task(base=CaptureFailure)
def product_export(store_id, product_id, user_id, publish=None):
    try:
        user = User.objects.get(id=user_id)

        store = CommerceHQStore.objects.get(id=store_id)
        product = CommerceHQProduct.objects.get(id=product_id)

        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)

        if publish is not None:
            product.update_data({'published': publish})

        product.store = store
        product.save()

        p = product.parsed

        images = []
        variants_thmbs = {}
        thumbs_idx = {}
        thumbs_uploads = {}
        variants_uploads = {}

        have_variant_images = False

        if type(p.get('variants_images')) is list:
            p['variants_images'] = {}
            product.update_data({'variants_images': {}})

        for h, var in list(p.get('variants_images', {}).items()):
            for idx, img in enumerate(p.get('images', [])):
                if hash_url_filename(img) == h:
                    variants_thmbs[var] = img
                    thumbs_idx[idx] = var

                    have_variant_images = True

        thumb_keys = list(thumbs_idx.values())
        variant_values = []
        for variant in p.get('variants', []):
            for value in variant.get('values', []):
                variant_values.append(value)

        have_variant_images = bool(set(variant_values) & set(thumb_keys))

        upload_session = store.request
        for idx, img in enumerate(p.get('images', [])):
            is_thumb = idx in thumbs_idx

            store.pusher_trigger('product-export', {
                'product': product.id,
                'progress': 'Uploading Images ({:,.2f}%)'.format(((idx + 1) * 100 / len(p['images'])) - 1),
            })

            content = requests.get(add_http_schema(img))
            mimetype = get_mimetype(img, default=content.headers.get('Content-Type'))
            filename = get_filename_from_url(img)

            if is_thumb:
                # Upload the variant thumbnail
                r = upload_session.post(
                    url=store.get_api_url('files'),
                    files={'files': (filename, content.content, mimetype, {'Expires': '0'})},
                    data={'type': 'thumbnails'}
                )

                r.raise_for_status()

                for j in r.json():
                    if idx in thumbs_idx:
                        thumbs_uploads[thumbs_idx[idx]] = j['id']

                # Upload the variant image
                r = upload_session.post(
                    url=store.get_api_url('files'),
                    files={'files': (filename, content.content, mimetype, {'Expires': '0'})},
                    data={'type': 'variant_images'}
                )

                r.raise_for_status()

                for j in r.json():
                    if idx in thumbs_idx:
                        variants_uploads[thumbs_idx[idx]] = j['id']

            else:
                r = upload_session.post(
                    url=store.get_api_url('files'),
                    files={'files': (filename, content.content, mimetype, {'Expires': '0'})},
                    data={'type': 'variant_images' if have_variant_images else 'product_images'}
                )

                r.raise_for_status()

                for j in r.json():
                    images.append(j['id'])

        is_multi = len(p['variants']) > 0

        weight = p.get('weight', 1.0)
        if p['weight_unit'] == 'g':
            weight = safe_float(weight, 0.0) / 1000.0
        elif p['weight_unit'] == 'lb':
            weight = safe_float(weight, 0.0) * 0.45359237
        elif p['weight_unit'] == 'oz':
            weight = safe_float(weight, 0.0) * 0.0283495
        else:
            weight = safe_float(weight, 0.0)

        weight = '{:.02f}'.format(weight)

        api_data = {
            'is_draft': not p['published'],
            'title': normalize_product_title(p['title']),
            'is_multi': is_multi,
            'textareas': [{
                'active': True,
                'text': p['description'],
                'name': 'Description'
            }],
            'images': [] if have_variant_images else images,

            'vendor': p['vendor'],
            'tags': p.get('tags', '').split(','),
            'type': p.get('type') or 'Default',
            'shipping_weight': weight,

            'price': safe_float(p['price']),
            'compare_price': safe_float(p['compare_at_price'], ''),

            'options': [],
            'variants': [],
        }

        if is_multi:
            for var in p['variants']:
                option = {
                    'title': var['title'],
                    'values': var['values'],
                    'thumbnails': []
                }

                for v in var['values']:
                    if v in thumbs_uploads:
                        option['thumbnails'].append({
                            'value': v,
                            'image': thumbs_uploads[v]
                        })

                        option['changes_look'] = True

                api_data['options'].append(option)

            vars_list = []
            for v in p['variants']:
                vars_list.append(v['values'])

            vars_list = all_possible_cases(vars_list)

            product_price = safe_float(p['price'])
            product_compare_at = safe_float(p['compare_at_price'], '')
            for idx, variants in enumerate(vars_list):
                if type(variants) is list:
                    title = ' / '.join(variants)
                else:
                    title = variants
                    variants = [variants]

                sku = []
                image = None
                for v in variants:
                    if v in p.get('variants_sku', []):
                        sku.append(p['variants_sku'][v])

                    if not image and v in variants_uploads:
                        image = variants_uploads[v]

                data_variants_info = p.get('variants_info', {}).get(title, {})
                var_info = {
                    'default': idx == 0,
                    'title': title,
                    'price': safe_float(data_variants_info.get('price'), product_price),
                    'compare_price': safe_float(data_variants_info.get('compare_at'), product_compare_at),
                    'shipping_weight': weight,
                    'variant': variants,
                    'images': []
                }

                if image:
                    var_info['images'] = [image]

                    for j in images:
                        var_info['images'].append(j)

                api_data['variants'].append(var_info)

        rep = store.request.post(
            url=store.get_api_url('products'),
            json=api_data
        )

        rep.raise_for_status()

        product.source_id = rep.json()['id']
        product.save()

        post_churnzero_product_export(user, product.title)

        store.pusher_trigger('product-export', {
            'success': True,
            'product': product.id,
            'product_url': reverse('chq:product_detail', kwargs={'pk': product.id}),
            'commercehq_url': product.commercehq_url
        })

    except CommerceHQProduct.DoesNotExist:
        store.pusher_trigger('product-export', {
            'success': False,
            'error': 'Product Not Found',
        })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        store.pusher_trigger('product-export', {
            'success': False,
            'error': format_chq_errors(e),
            'product': product.id,
            'product_url': reverse('chq:product_detail', kwargs={'pk': product.id}),
        })


@celery_app.task(base=CaptureFailure)
def product_update(product_id, data):
    try:
        product = CommerceHQProduct.objects.get(id=product_id)
        store = product.store

        p = product.retrieve()
        p['title'] = data['title']
        p['type'] = data['type']
        p['tags'] = data.get('tags', '').split(',')
        p['vendor'] = data['vendor']
        p['is_draft'] = not data['published']
        p['price'] = data['price']
        p['compare_price'] = data['compare_price']

        if 'weight_unit' in p and 'weight' in p:
            weight = p.get('weight', 1.0)

            if p['weight_unit'] == 'g':
                weight = safe_float(weight, 0.0) / 1000.0
            elif p['weight_unit'] == 'lb':
                weight = safe_float(weight, 0.0) * 0.45359237
            elif p['weight_unit'] == 'oz':
                weight = safe_float(weight, 0.0) * 0.0283495
            else:
                weight = safe_float(weight, 0.0)

            p['shipping_weight'] = '{:.02f}'.format(weight)

        for idx, textarea in enumerate(p['textareas']):
            if textarea['name'] == 'Description':
                p['textareas'][idx]['text'] = data['description']

        for idx, variant in enumerate(p.get('variants', [])):
            for v in data['variants']:
                if v['id'] == variant['id']:
                    p['variants'][idx]['price'] = v['price']
                    p['variants'][idx]['compare_price'] = v['compare_price']
                    p['variants'][idx]['sku'] = v['sku']

        product_images = [j['path'] for j in p['images']]
        variant_images = []
        for j in p.get('variants', []):
            for k in j['images']:
                variant_images.append(k['path'])

        have_variant_images = len(set(variant_images)) > len(product_images)

        images_need_delete = []
        common_images = product.get_common_images()
        if have_variant_images:
            for j in p.get('variants', []):
                for k in j['images']:
                    if k['path'] not in data['images'] and k['path'] in common_images:
                        images_need_delete.append(k['id'])
        else:
            for j in p['images']:
                if j['path'] not in data['images']:
                    images_need_delete.append(j['id'])

        images_need_upload = []
        for img in data['images']:
            if img not in product_images + variant_images:
                images_need_upload.append(img)

        for idx, img in enumerate(images_need_upload):
            store.pusher_trigger('product-update', {
                'product': product.id,
                'progress': 'Uploading Images ({:,.2f}%)'.format(((idx + 1) * 100 / len(images_need_upload)) - 1),
            })

            content = requests.get(add_http_schema(img))
            mimetype = get_mimetype(img, default=content.headers.get('Content-Type'))

            r = store.request.post(
                url=store.get_api_url('files'),
                files={'files': (get_filename_from_url(img), content.content, mimetype, {'Expires': '0'})},
                data={'type': 'variant_images' if have_variant_images else 'product_images'}
            )

            r.raise_for_status()

            for j in r.json():
                if have_variant_images:
                    for idx, v in enumerate(p['variants']):
                        p['variants'][idx]['images'].append(j['id'])
                else:
                    p['images'].append(j['id'])

        if have_variant_images:
            for idx, v in enumerate(p['variants']):
                new_images = []
                for i, image in enumerate(p['variants'][idx]['images']):
                    if type(image) is int:
                        new_images.append(image)
                        continue
                    if 'id' in image and image['id'] not in images_need_delete:
                        new_images.append(image['id'])
                p['variants'][idx]['images'] = new_images

            for i, image in enumerate(p['images']):
                if type(image) is int:
                    continue
                if 'id' in image:
                    p['images'][i] = image['id']
        else:
            new_images = []
            for i, image in enumerate(p['images']):
                if type(image) is int:
                    new_images.append(image)
                    continue
                if 'id' in image and image['id'] not in images_need_delete:
                    new_images.append(image['id'])
            p['images'] = new_images

        for i, option in enumerate(p.get('options', [])):
            for j, thumb in enumerate(option['thumbnails']):
                if type(thumb.get('image')) is dict:
                    p['options'][i]['thumbnails'][j]['image'] = thumb['image']['id']

        rep = store.request.patch(
            url='{}/{}'.format(store.get_api_url('products'), product.source_id),
            json=p
        )

        rep.raise_for_status()

        product.source_id = rep.json()['id']
        product.save()

        store.pusher_trigger('product-update', {
            'success': True,
            'product': product.id,
            'product_url': reverse('chq:product_detail', kwargs={'pk': product.id})
        })

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        store.pusher_trigger('product-update', {
            'success': False,
            'error': format_chq_errors(e),
            'product': product.id,
            'product_url': reverse('chq:product_detail', kwargs={'pk': product.id})
        })


@celery_app.task(bind=True, base=CaptureFailure)
def create_image_zip(self, images, product_id):
    from leadgalaxy.utils import aws_s3_upload

    try:
        product = CommerceHQProduct.objects.get(pk=product_id)
        filename = mktemp(suffix='.zip', prefix='{}-'.format(product_id))

        with ZipFile(filename, 'w') as images_zip:
            for i, img_url in enumerate(images):
                img_url = add_http_schema(img_url)

                image_name = 'image-{}.{}'.format(i + 1, get_fileext_from_url(img_url, fallback='jpg'))
                images_zip.writestr(image_name, requests.get(img_url).content)

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


@celery_app.task(base=CaptureFailure, bind=True)
def order_save_changes(self, data):
    order_id = None
    try:
        updater = CHQOrderUpdater()
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
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        if not self.request.called_directly:
            countdown = retry_countdown('retry_ordered_tags_{}'.format(order_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def products_supplier_sync(self, store_id, products, sync_price, price_markup, compare_markup, sync_inventory, cache_key):
    store = CommerceHQStore.objects.get(id=store_id)
    products = CommerceHQProduct.objects.filter(id__in=products, user=store.user, store=store, source_id__gt=0)
    total_count = 0
    for product in products:
        if product.have_supplier() and product.default_supplier.is_aliexpress:
            total_count += 1

    push_data = {
        'task': self.request.id,
        'count': total_count,
        'success': 0,
        'fail': 0,
    }
    store.pusher_trigger('products-supplier-sync', push_data)

    for product in products:
        if not product.have_supplier() or not product.default_supplier.is_aliexpress:
            continue

        commercehq_id = product.source_id
        supplier = product.default_supplier
        push_data['id'] = product.id
        push_data['title'] = product.title
        push_data['commercehq'] = product.commercehq_url
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
            # Fetch commercehq variants
            product_data = get_chq_product(store, commercehq_id)
        except Exception:
            push_data['status'] = 'fail'
            push_data['error'] = 'Failed to load commercehq data'
            push_data['fail'] += 1
            store.pusher_trigger('products-supplier-sync', push_data)
            continue

        try:
            # Check if there's only one price
            same_price = (len('variants') == 1
                          or len(set([v['price'] for v in product_data['variants']])) == 1
                          or len(supplier_variants) == 1
                          or supplier_min_price == supplier_max_price)
            # New Data
            updated = False
            mapped_variants = {}
            unmapped_variants = []

            if sync_price and same_price:
                # Use one price for all variants
                for i, variant in enumerate(product_data['variants']):
                    variant['price'] = round(supplier_max_price * (100 + price_markup) / 100.0, 2)
                    variant['compare_at_price'] = round(supplier_variants[i]['price'] * (100 + compare_markup) / 100.0, 2)
                    updated = True

            if (sync_price and not same_price) or sync_inventory:
                for i, variant in enumerate(supplier_variants):
                    sku = variant.get('sku')
                    if not sku:
                        if len(product_data['variants']) == 1 and len(supplier_variants) == 1:
                            idx = 0
                        else:
                            continue
                    else:
                        idx = variant_index_from_supplier_sku(product, sku, product_data['variants'])

                        if idx is None:
                            if len(product_data['variants']) == 1 and len(supplier_variants) == 1:
                                idx = 0
                            else:
                                continue

                    mapped_variants[str(product_data['variants'][idx]['id'])] = True
                    # Sync price
                    if sync_price and not same_price:
                        variant['price'] = round(supplier_variants[idx]['price'] * (100 + price_markup) / 100.0, 2)
                        variant['compare_at_price'] = round(supplier_variants[idx]['price'] * (100 + compare_markup) / 100.0, 2)
                        updated = True

                # check unmapped variants
                for variant in product_data['variants']:
                    if not mapped_variants.get(str(variant['id']), False):
                        unmapped_variants.append(variant['title'])

            if updated:
                rep = store.request.patch(
                    url='{}/{}'.format(store.get_api_url('products'), commercehq_id),
                    json={
                        'variants': product_data['variants']
                    }
                )

                rep.raise_for_status()

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
