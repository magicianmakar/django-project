import json
import itertools

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.template.defaultfilters import truncatewords

from raven.contrib.django.raven_compat.models import client as raven_client
from pusher import Pusher

from app.celery_base import celery_app, CaptureFailure, retry_countdown

from shopified_core import permissions
from shopified_core import utils

from .models import GrooveKartStore, GrooveKartProduct, GrooveKartSupplier
from .utils import GrooveKartOrderUpdater, format_gkart_errors


@celery_app.task(base=CaptureFailure)
def product_save(req_data, user_id):
    User = get_user_model()
    store = req_data.get('store')
    data = req_data['data']
    product_data = req_data.get('product')
    user = User.objects.get(id=user_id)
    from_extension = 'access_token' in req_data
    extra_context = {'store': store, 'product': product_data, 'from_extension': from_extension}
    raven_client.extra_context(extra_context)

    if store:
        try:
            store = GrooveKartStore.objects.get(id=store)
            permissions.user_can_view(user, store)
        except (GrooveKartStore.DoesNotExist, ValueError):
            raven_client.captureException()
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
        raven_client.captureException(extra={'original_url': original_url})

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
            raven_client.captureException()
            return {'error': "Product {} does not exist".format(req_data['product'])}
        except PermissionDenied as e:
            raven_client.captureException()
            return {'error': "Product: {}".format(str(e))}

        product.update_data(data)
        product.store = store
        product.save()

    else:  # New product to save

        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)
        if not can_add:
            return {
                'error': 'Your current plan allow up to %d saved products, currently you have %d saved products.'
                         % (total_allowed, user_count)
            }

        try:
            product = GrooveKartProduct(store=store, user=user.models_user)
            product.update_data(data)
            permissions.user_can_add(user, product)
            product.save()

            store_info = json.loads(data).get('store')

            supplier = GrooveKartSupplier.objects.create(
                store=store,
                product=product,
                product_url=original_url,
                supplier_name=store_info.get('name'),
                supplier_url=store_info.get('url'),
                is_default=True
            )

            product.set_default_supplier(supplier, commit=True)

        except PermissionDenied as e:
            raven_client.captureException()
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
def product_export(store_id, product_id, user_id):
    user = get_user_model().objects.get(id=user_id)
    store = GrooveKartStore.objects.get(id=store_id)
    product = GrooveKartProduct.objects.get(id=product_id)
    product_url = reverse('gkart:product_detail', kwargs={'pk': product.id})
    pusher_data = {'success': False, 'product': product.id, 'product_url': product_url}

    if product.source_id and product.store.id == store.id:
        pusher_data['error'] = 'Product already connected to GrooveKart store.'
        return store.pusher_trigger('product-export', pusher_data)

    try:
        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)
        product_data = product.parsed
        tags = product_data.get('tags').split(',')
        variants = product_data.get('variants', [])
        variant_groups = []

        api_data = {
            'product': {
                'title': product_data.get('title'),
                'body_html': product_data.get('description'),
                'vendor': product_data.get('vendor'),
                'price': product_data.get('price'),
                'weight': product_data.get('weight'),
                'compare_default_price': product_data.get('compare_at_price'),
                'product_type': product_data.get('type'),
                'sku': product_data.get('sku'),
                'tags': ', '.join(tags),
            },
        }

        if variants:
            for variant in variants:
                variant_groups.append({"name": variant['title'], "group_type": "select"})

            api_data['product']['variant_groups'] = variant_groups

        endpoint = store.get_api_url('products.json')
        r = store.request.post(endpoint, json=api_data)
        r.raise_for_status()
        product.store = store
        groovekart_product = r.json()
        product.source_id = groovekart_product['id_product']
        product.save()

        images = product_data.get('images', [])
        api_images = []
        if images:
            for index, image in enumerate(images):
                api_data = {
                    'product': {
                        'id': product.source_id,
                        'image': {'src': image, 'position': index},
                    }
                }
                # The API only allows images to be uploaded one at a time
                r = store.request.post(endpoint, json=api_data)
                r.raise_for_status()
                api_images.append({'url': image, 'id': r.json().get('id_image')})

        if variants:
            # e.g. Color, Size
            titles = []
            # e.g. Red, LARGE
            values = []

            for variant in variants:
                titles.append(variant['title'])
                values.append(variant['values'])

            # Iterates through all possible variants e.g. [(RED, LARGE), (RED, SMALL)]
            product_variants = []

            for index, attributes in enumerate(itertools.product(*values)):
                variant_data = {
                    'compare_at_price': product_data.get('compare_at_price'),
                    'weight': product_data.get('weight'),
                    'price': product_data.get('price'),
                    'default_on': 1 if index == 0 else 0,
                    'image_id': api_images[0]['id'],
                    'variant_values': {}
                }

                for label, value in zip(titles, attributes):
                    # e.g. label = Color, value = RED
                    variant_data['variant_values'][label] = value

                product_variants.append(variant_data)

            api_data = {
                'action': 'add',
                'product_id': product.source_id,
                'variants': product_variants,
                'variant_groups': variant_groups,
            }
            variants_endpoint = store.get_api_url('variants.json')
            r = store.request.post(variants_endpoint, json=api_data)
            r.raise_for_status()
            product.sync()

            if product.default_supplier:
                variants_mapping = {}
                for variant in product.parsed.get('variants'):
                    variant_id = variant.get('id')
                    if variant_id not in variants_mapping:
                        variants_mapping[variant_id] = []

                    variants_mapping[variant_id].append({'title': variant.get('variant_name')})

                for variant_id in variants_mapping:
                    variants_mapping[variant_id] = json.dump(variants_mapping[variant_id])

                product.default_supplier.variants_map = json.dumps(variants_mapping)
                product.default_supplier.save()

        api_data = {
            'product': {
                'id': product.source_id,
                'action': 'product_status',
                'active': product.parsed.get('published', False),
            }
        }
        r = store.request.post(endpoint, json=api_data)
        r.raise_for_status()

        # Update variant image_hash
        if product_data.get('variants_images') and api_images:
            image_id_by_hash = {}
            for image in api_images:
                hash_ = utils.hash_url_filename(image['url'])
                image_id_by_hash[hash_] = image['id']

            saved_variants = product.parsed.get('variants')
            for image_hash, variant_name in product_data.get('variants_images').items():
                api_data = {
                    'image_id': image_id_by_hash[image_hash],
                    'variants': []
                }
                for variant in saved_variants:
                    if variant_name in GrooveKartProduct.get_variant_options(variant):
                        api_data['variants'].append(variant['id'])

                if len(api_data['variants']) > 0:
                    variants_endpoint = store.get_api_url('variants.json')
                    r = store.request.post(variants_endpoint, json=api_data)
                    r.raise_for_status()

        pusher_data['success'] = True

        return store.pusher_trigger('product-export', pusher_data)

    except Exception as e:
        response = e.response.text if hasattr(e, 'response') else ''
        raven_client.captureException(extra={'response': response})
        pusher_data['error'] = format_gkart_errors(e)

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
            variants.append({
                'id': variant.get('id'),
                'price': f'{variant.get("price"):,.2f}',
                'compare_at_price': f'{variant.get("compare_at_price"):,.2f}'
            })

        api_data = {
            'action': 'update',
            'product_id': product.source_id,
            'variants': variants,
        }
        variants_endpoint = store.get_api_url('variants.json')
        r = store.request.post(variants_endpoint, json=api_data)
        r.raise_for_status()

        product_data = product.parsed
        images = product_data.get('images', [])
        if images:
            for index, image in enumerate(images):
                api_data = {
                    'product': {
                        'id': product.source_id,
                        'image': {'src': image, 'position': index},
                    }
                }
                r = store.request.post(endpoint, json=api_data)
                r.raise_for_status()

        pusher_data['success'] = True

        return store.pusher_trigger('product-update', pusher_data)

    except Exception as e:
        response = e.response.text if hasattr(e, 'response') else ''
        raven_client.captureException(extra={'response': response})
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
            stores_data.append({
                'id': store.id,
                'products_connected': 0,
                'products_saved': 0,
                'pending_orders': 0,
            })

        cache.set('gkart_user_statistics_{}'.format(user_id), stores_data, timeout=3600)

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger("user_{}".format(user_id), 'gkart-user-statistics-calculated', {'task': self.request.id})

    except:
        raven_client.captureException()


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
        raven_client.captureException(extra=utils.http_exception_response(e))

        if not self.request.called_directly:
            countdown = retry_countdown('retry_ordered_tags_{}'.format(order_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)
