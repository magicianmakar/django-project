import json
import itertools
import re
from tempfile import mktemp
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.template.defaultfilters import truncatewords
from django.utils.text import slugify

import requests
from lib.exceptions import capture_exception
from pusher import Pusher

from app.celery_base import celery_app, CaptureFailure, retry_countdown

from shopified_core import permissions
from shopified_core import utils
from shopified_core.utils import safe_str

from churnzero_core.utils import post_churnzero_product_import, post_churnzero_product_export
from .models import GrooveKartStore, GrooveKartProduct, GrooveKartSupplier
from .utils import (
    OrderListQuery,
    GrooveKartOrderUpdater,
    format_gkart_errors,
    get_variant_value,
    update_product_images,
    get_or_create_category_by_title
)

from product_alerts.utils import (
    get_supplier_variants,
    variant_index_from_supplier_sku
)


@celery_app.task(base=CaptureFailure)
def product_save(req_data, user_id):
    User = get_user_model()
    store = req_data.get('store')
    data = req_data['data']
    user = User.objects.get(id=user_id)
    # raven_client.extra_context({'store': store, 'product': req_data.get('product'), 'from_extension': 'access_token' in req_data})

    if store:
        try:
            store = GrooveKartStore.objects.get(id=store)
            permissions.user_can_view(user, store)
        except (GrooveKartStore.DoesNotExist, ValueError):
            capture_exception()
            return {'error': 'Selected store (%s) not found' % (store)}
        except PermissionDenied as e:
            return {'error': "Store: {}".format(str(e))}
    else:
        store = user.profile.get_gkart_stores().first()

    original_url = json.loads(data).get('original_url')
    if not original_url:
        original_url = req_data.get('original_url')

    try:
        import_store = utils.get_domain(original_url)
    except:
        capture_exception(extra={'original_url': original_url})

        return {'error': 'Original URL is not set.'}

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
            product = GrooveKartProduct.objects.get(id=req_data['product'])
            permissions.user_can_edit(user, product)
        except GrooveKartProduct.DoesNotExist:
            capture_exception()
            return {'error': "Product {} does not exist".format(req_data['product'])}
        except PermissionDenied as e:
            capture_exception()
            return {'error': "Product: {}".format(str(e))}

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
            product = GrooveKartProduct(store=store, user=user.models_user)
            product.update_data(data)
            user_supplement_id = json.loads(data).get('user_supplement_id')
            product.user_supplement_id = user_supplement_id
            permissions.user_can_add(user, product)
            product.save()

            store_info = json.loads(data).get('store')

            supplier = GrooveKartSupplier.objects.create(
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
            'url': reverse('gkart:product_detail', kwargs={'pk': product.id}),
            'id': product.id,
        }
    }


@celery_app.task(base=CaptureFailure)
def product_export(store_id, product_id, user_id, publish=None):
    user = get_user_model().objects.get(id=user_id)
    store = GrooveKartStore.objects.get(id=store_id)
    product = GrooveKartProduct.objects.get(id=product_id)
    product_url = reverse('gkart:product_detail', kwargs={'pk': product.id})
    pusher_data = {'success': False, 'product': product.id, 'product_url': product_url}

    if product.source_id and product.store.id == store.id:
        pusher_data['error'] = 'Product already connected to GrooveKart store.'
        return store.pusher_trigger('product-export', pusher_data)

    try:
        product.update_data({'exporting': True})
        product.save()

        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)
        product_data = product.parsed
        tags = utils.safe_str(product_data.get('tags')).split(',')
        variants_images = product_data.get('variants_images') or {}
        images = product_data.get('images', [])
        variants = product_data.get('variants', [])
        # variants_sku = product_data.get('variants_sku', {})

        category_id = None
        if product_data.get('type'):
            category_id = get_or_create_category_by_title(store, product_data.get('type'))

        api_data = {
            'product': {
                # Remove special chars from title
                'title': re.sub(r'#|\?|=', '-', product_data.get('title') or ''),
                'body_html': product_data.get('description'),
                # Remove default value when vendor is not required anymore
                'vendor': product_data.get('vendor') or '-',
                'price': product_data.get('price'),
                'weight': product_data.get('weight'),
                'compare_default_price': product_data.get('compare_at_price'),
                'category_id': category_id,
                'sku': product_data.get('sku'),
                'tags': ', '.join(tags),
            },
        }

        first_image = images[0]
        images = images[1:]
        api_data['product']['image'] = {
            'src': first_image,
            'position': 0
        }

        product_variants = []
        if variants:
            # Prepare color textures
            color_textures = {}
            if variants_images:
                for image in images:
                    hash_ = utils.hash_url_filename(image)
                    variant_name = variants_images.get(hash_)
                    if variant_name:
                        color_textures[variant_name] = image

            # e.g. Color, Size
            titles = []
            # e.g. Red, LARGE
            values = []

            for variant in variants:
                titles.append(variant['title'])
                values.append(variant['values'])

            # Iterates through all possible variants e.g. [(RED, LARGE), (RED, SMALL)]
            for index, attributes in enumerate(itertools.product(*values)):
                data_variants_info = product_data.get('variants_info', {}).get(' / '.join(attributes), {})

                variant_data = {
                    'weight': product_data.get('weight'),
                    'compare_at_price': utils.safe_float(data_variants_info.get('price'), product_data.get('compare_at_price')),
                    'price': utils.safe_float(data_variants_info.get('price'), product_data.get('price')),
                    'default_on': 1 if index == 0 else 0,
                    'variant_values': {},
                    'sku': [],
                }

                for label, value in zip(list(reversed(titles)), list(reversed(attributes))):
                    # variant_data['sku'].append(variants_sku.get(value))  # TODO: max-length of 32 for now
                    label, value = get_variant_value(label, value, color_textures)
                    variant_data['variant_values'][label] = value

                variant_data['sku'] = ';'.join(variant_data['sku'])
                product_variants.append(variant_data)
            api_data['product']['variants'] = product_variants

        endpoint = store.get_api_url('products.json')
        r = store.request.post(endpoint, json=api_data)
        r.raise_for_status()

        product.store = store
        groovekart_product = r.json()
        try:
            product.source_id = groovekart_product['id_product']
        except KeyError:
            capture_exception(extra={'api_data': api_data, 'response': r.text})

            error = utils.dict_val(groovekart_product, ['error', 'Error'])
            if isinstance(error, dict):
                error = error.get('message')

            pusher_data['error'] = str(error)
            return store.pusher_trigger('product-export', pusher_data)

        product.sync()

        if product.default_supplier:
            variants_mapping = {}
            for variant in product.parsed.get('variants'):
                variant_id = variant.get('id')
                if variant_id not in variants_mapping:
                    variants_mapping[variant_id] = []

                variant_titles = [{'title': t} for t in GrooveKartProduct.get_variant_options(variant)]
                variants_mapping[variant_id].extend(variant_titles)

            for variant_id in variants_mapping:
                variants_mapping[variant_id] = json.dumps(variants_mapping[variant_id])

            if variants_mapping:
                product.default_supplier.variants_map = json.dumps(variants_mapping)
            else:
                product.default_supplier.variants_map = None

            product.default_supplier.save()

        active = publish if publish is not None else product.parsed.get('published', False)

        api_data = {
            'product': {
                'id': product.source_id,
                'action': 'product_status',
                'active': active,
            }
        }
        r = store.request.post(endpoint, json=api_data)
        r.raise_for_status()

        # Too many images to export in the same thread
        product_export_images.s(store_id, product_id, images, variants_images).apply_async()

        pusher_data['commercehq_url'] = groovekart_product.get('product_url')
        pusher_data['success'] = True

        post_churnzero_product_export(user, product.title)

        return store.pusher_trigger('product-export', pusher_data)

    except Exception as e:
        response = e.response.text if hasattr(e, 'response') else ''
        capture_exception(extra={'response': response})
        pusher_data['error'] = format_gkart_errors(e)

        return store.pusher_trigger('product-export', pusher_data)


@celery_app.task(base=CaptureFailure)
def product_export_images(store_id, product_id, images, variants_images):
    store = GrooveKartStore.objects.get(id=store_id)
    product = GrooveKartProduct.objects.get(id=product_id)
    product_data = product.parsed
    pusher_data = {'success': False, 'product': product.id}

    try:
        if not images:
            product.update_data({'exporting': False})
            product.save()
            pusher_data['success'] = True
            return store.pusher_trigger('product-export', pusher_data)

        unassigned_images = []
        update_variants_api_data = {
            'action': 'update',
            'product_id': utils.safe_int(product.source_id),
            'variants': []
        }
        total = len(images)
        for index, image in enumerate(images[::-1]):
            api_data = {
                'product': {
                    'id': product.source_id,
                    'image': {'src': image, 'position': index},
                }
            }

            store.pusher_trigger('product-export', {
                'product': product.id,
                'progress': 'Updating Images ({:,.2f}%)'.format(((index + 1) * 100 / total) - 1),
            })

            # The API only allows images to be uploaded one at a time
            endpoint = store.get_api_url('products.json')
            r = store.request.post(endpoint, json=api_data)
            r.raise_for_status()

            json_image = r.json()
            image_id = utils.safe_int(json_image.get('id_image'))
            hash_ = utils.hash_url_filename(image)

            # Assign default image to variant
            if variants_images.get(hash_):
                variant_name = variants_images.get(hash_)
                for variant in product_data.get('variants', []):
                    if variant_name in GrooveKartProduct.get_variant_options(variant):
                        update_variants_api_data['variants'].append({
                            'id': utils.safe_int(variant['id']),
                            'image_id': [image_id],
                            'price': variant.get('price'),
                            'compare_at_price': variant.get('compare_price'),
                            'weight': variant.get('weight'),
                            'default_on': variant.get('default_on'),
                            'update_all_fields': False,
                            # 'sku': variant.get('sku'),  # Not working
                        })
            else:
                unassigned_images.append(image_id)

        for v in update_variants_api_data['variants']:
            v['image_id'] += unassigned_images

        # Update variants with default image
        variants_endpoint = store.get_api_url('variants.json')
        if len(update_variants_api_data['variants']) > 0:
            r = store.request.post(variants_endpoint, json=update_variants_api_data)
            r.raise_for_status()

        product.update_data({'exporting': False})
        product.sync()

        pusher_data['success'] = True

        return store.pusher_trigger('product-export', pusher_data)

    except Exception as e:
        response = e.response.text if hasattr(e, 'response') else ''
        capture_exception(extra={'response': response})
        pusher_data['error'] = format_gkart_errors(e)

        product.update_data({'exporting': False})
        product.save()

        return store.pusher_trigger('product-export', pusher_data)


@celery_app.task(base=CaptureFailure)
def product_update(product_id, data):
    product = GrooveKartProduct.objects.get(id=product_id)
    product_url = reverse('gkart:product_detail', kwargs={'pk': product.id})
    store = product.store
    product.update_data({'type': data.get('type', '')})
    product.save()
    pusher_data = {'success': False, 'product': product.id, 'product_url': product_url}

    try:
        tags = data.get('tags').split(',')

        api_data = {
            'product': {
                'action': 'update_product',
                'id': product.source_id,
                'title': data.get('title'),
                'description': data.get('description'),
                'vendor': data.get('vendor'),
                'price': data.get('price'),
                'compare_default_price': data.get('compare_at_price'),
                'sku': data.get('sku'),
                'tags': {
                    'tags_list': ','.join(tags),
                    'delete_existing': True,
                },
            },
        }

        endpoint = store.get_api_url('products.json')
        r = store.request.post(endpoint, json=api_data)
        r.raise_for_status()

        variants = []
        for variant in data.get('variants'):
            info = {
                'id': variant.get('id'),
                'price': f'{variant.get("price"):,.2f}',
            }

            if variant.get("compare_at_price"):
                info['compare_at_price'] = f'{variant.get("compare_at_price"):,.2f}'

            variants.append(info)

        api_data = {
            'action': 'update',
            'product_id': product.source_id,
            'variants': variants,
        }
        variants_endpoint = store.get_api_url('variants.json')
        r = store.request.post(variants_endpoint, json=api_data)
        r.raise_for_status()

        update_product_images(product, data.get('images', []))

        pusher_data['success'] = True

        return store.pusher_trigger('product-update', pusher_data)

    except Exception as e:
        response = e.response.text if hasattr(e, 'response') else ''
        capture_exception(extra={'response': response})
        pusher_data['error'] = format_gkart_errors(e)

        return store.pusher_trigger('product-update', pusher_data)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def calculate_user_statistics(self, user_id):
    try:
        User = get_user_model()
        user = User.objects.get(id=user_id)
        stores = user.profile.get_gkart_stores()

        stores_data = []
        for store in stores:
            # Payment Accepted -> 2
            order_query = OrderListQuery(store, {'order_status': '2'})

            stores_data.append({
                'id': store.id,
                'products_connected': store.connected_count(),
                'products_saved': store.saved_count(),
                'pending_orders': order_query.count(attempts=2),
            })

        cache.set('gkart_user_statistics_{}'.format(user_id), stores_data, timeout=3600)

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger("user_{}".format(user_id), 'gkart-user-statistics-calculated', {'task': self.request.id})

    except:
        capture_exception()


@celery_app.task(base=CaptureFailure, bind=True)
def order_save_changes(self, data):
    order_id = None
    try:
        updater = GrooveKartOrderUpdater()
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
        capture_exception(extra=utils.http_exception_response(e))

        if not self.request.called_directly:
            countdown = retry_countdown('retry_ordered_tags_{}'.format(order_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(bind=True, base=CaptureFailure)
def create_image_zip(self, images, product_id):
    from leadgalaxy.utils import aws_s3_upload

    try:
        product = GrooveKartProduct.objects.get(pk=product_id)
        filename = mktemp(suffix='.zip', prefix='{}-'.format(product_id))

        with ZipFile(filename, 'w') as images_zip:
            for i, img_url in enumerate(images):
                img_url = utils.add_http_schema(img_url)

                image_name = 'image-{}.{}'.format(i + 1, utils.get_fileext_from_url(img_url, fallback='jpg'))
                images_zip.writestr(image_name, requests.get(img_url).content)

        product_filename = 'product-images.zip'
        title_slug = slugify(product.title)
        if title_slug:
            product_filename = f'{title_slug[:100]}-images.zip'

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


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def products_supplier_sync(self, store_id, products, sync_price, price_markup, compare_markup, sync_inventory, cache_key):
    store = GrooveKartStore.objects.get(id=store_id)
    products = GrooveKartProduct.objects.filter(id__in=products, user=store.user, store=store, source_id__gt=0)
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

        supplier = product.default_supplier
        push_data['id'] = product.id
        push_data['title'] = product.title
        push_data['groovekart_link'] = product.groovekart_url
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

        product_data = {}

        try:
            # Fetch groovekart variants
            product_data = product.parsed

        except Exception:
            push_data['status'] = 'fail'
            push_data['error'] = 'Failed to load groove kart data'
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

                        if idx is not None:
                            variant_id = utils.safe_int(product_data['variants'][idx]['id_product_variant'])
                        if variant_id > 0:
                            product_data['variants'][idx]['quantity'] = variant['availabe_qty']
                        elif len(product_data.get('variants', [])) == 0 or variant_id < 0:
                            product_data['quantity'] = variant['availabe_qty']
                        if idx is None:
                            if len(product_data['variants']) == 1 and len(supplier_variants) == 1:
                                idx = 0
                            else:
                                continue

                    mapped_variants[str(product_data['variants'][idx]['id_product_variant'])] = True
                    # Sync price
                    if sync_price and not same_price:
                        variant['price'] = round(supplier_variants[idx]['price'] * (100 + price_markup) / 100.0, 2)
                        variant['compare_at_price'] = round(supplier_variants[idx]['price'] * (100 + compare_markup) / 100.0, 2)
                        updated = True

                # check unmapped variants
                for variant in product_data['variants']:
                    if not mapped_variants.get(str(variant['id']), False):
                        unmapped_variants.append(variant['title'])

            if updated or sync_inventory:
                api_data = {
                    'product': {
                        'action': 'update',
                        'product_id': product.source_id,
                        'variants': product_data['variants']
                    }
                }
                variants_endpoint = store.get_api_url('variants.json')
                r = store.request.post(variants_endpoint, json=api_data)
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
