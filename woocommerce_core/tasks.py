import simplejson as json

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse

from raven.contrib.django.raven_compat.models import client as raven_client

from app.celery import celery_app, CaptureFailure
from shopified_core import utils
from shopified_core import permissions

from .models import WooStore, WooProduct
from .utils import (
    format_woo_errors,
    get_product_api_data,
    get_image_id_by_hash,
    get_variants_api_data,
    add_store_tags_to_data,
)


@celery_app.task(base=CaptureFailure)
def product_save(req_data, user_id):
    store = req_data.get('store')
    data = req_data['data']

    user = User.objects.get(id=user_id)

    raven_client.extra_context({
        'store': store,
        'product': req_data.get('product'),
        'from_extension': ('access_token' in req_data)
    })

    if store:
        try:
            store = WooStore.objects.get(id=store)
            permissions.user_can_view(user, store)

        except (WooStore.DoesNotExist, ValueError):
            raven_client.captureException()

            return {
                'error': 'Selected store (%s) not found' % (store)
            }
        except PermissionDenied as e:
            return {
                'error': "Store: {}".format(e.message)
            }
    else:
        store = user.profile.get_woo_stores().first()

    original_url = json.loads(data).get('original_url')
    if not original_url:
        original_url = req_data.get('original_url')

    try:
        import_store = utils.get_domain(original_url)
    except:
        raven_client.captureException(extra={'original_url': original_url})

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
            raven_client.captureException()
            return {
                'error': "Product {} does not exist".format(req_data['product'])
            }

        except PermissionDenied as e:
            raven_client.captureException()
            return {
                'error': "Product: {}".format(e.message)
            }

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
            product = WooProduct(store=store, user=user.models_user)
            product.update_data(data)

            permissions.user_can_add(user, product)

            product.save()

        except PermissionDenied as e:
            raven_client.captureException()
            return {
                'error': "Add Product: {}".format(e.message)
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
        product.save()

        saved_data = product.parsed
        data = get_product_api_data(saved_data)
        data = add_store_tags_to_data(data, store, saved_data.get('tags', []))

        r = store.wcapi.post('products', data)
        r.raise_for_status()

        store_data = r.json()
        product.source_id = store_data['id']
        product.save()

        if saved_data.get('variants', []):
            image_id_by_hash = get_image_id_by_hash(store_data)
            variant_list = get_variants_api_data(saved_data, image_id_by_hash)
            path = 'products/{}/variations/batch'.format(product.source_id)
            r = store.wcapi.post(path, {'create': variant_list})
            r.raise_for_status()

        store.pusher_trigger('product-export', {
            'success': True,
            'product': product.id,
            'product_url': reverse('woo:product_detail', kwargs={'pk': product.id}),
            'woocommerce_url': product.woocommerce_url
        })

    except Exception as e:
        raven_client.captureException(extra={
            'response': e.response.text if hasattr(e, 'response') else ''
        })

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

        p = product.retrieve()
        p['name'] = data['title']
        p['status'] = 'draft' if not data['published'] else 'publish'
        p['price'] = data['price']
        p['regular_price'] = data['compare_price']
        p['weight'] = '{:.02f}'.format(data['weight'])

        data_tags = data['tags'].split(',')
        create = [{'name': data_tag} for data_tag in data_tags if data_tag]

        # Creates tags that haven't been created yet. Returns an error if tag exists.
        r = store.wcapi.post('products/tags/batch', {'create': create})
        r.raise_for_status()

        store_tags = r.json()['create']
        tag_ids = []
        for store_tag in store_tags:
            if 'id' in store_tag:
                tag_ids.append(store_tag['id'])
            if 'error' in store_tag:
                if store_tag['error'].get('code', '') == 'term_exists':
                    tag_ids.append(store_tag['error']['data']['resource_id'])

        p['tags'] = [{'id': tag_id} for tag_id in tag_ids]

        variants = p.pop('variants', [])
        if variants:
            for variant in variants:
                for variant_data in data['variants']:
                    if variant_data['id'] == variant['id']:
                        variant['price'] = variant_data['price']
                        variant['regular_price'] = variant_data['compare_price']
                        variant['sku'] = variant_data['sku']

            target = 'products/%s/variations/batch' % product.source_id
            r = store.wcapi.post(target, {'update': variants})
            r.raise_for_status()

        images = []
        data_images = data.get('images', [])
        product_images = p.get('images', [])
        product_image_srcs = [img['src'] for img in product_images]

        for product_image in product_images:
            # Skips the placeholder image
            if product_image['id'] == 0:
                continue
            # Keeps the images submitted in the data
            if product_image['src'] in data_images:
                images.append({'id': product_image['id'], 'position': product_image['position']})

        for data_image in data_images:
            if data_image not in product_image_srcs:
                images.append({'src': data_image})

        p['images'] = images if any(images) else ''

        r = store.wcapi.put('products/{}'.format(product.source_id), p)
        r.raise_for_status()

        product.source_id = r.json()['id']
        product.save()

        store.pusher_trigger('product-update', {
            'success': True,
            'product': product.id,
            'product_url': reverse('woo:product_detail', kwargs={'pk': product.id})
        })

    except Exception as e:
        raven_client.captureException(extra={
            'response': e.response.text if hasattr(e, 'response') else ''
        })

        store.pusher_trigger('product-update', {
            'success': False,
            'error': format_woo_errors(e),
            'product': product.id,
            'product_url': reverse('woo:product_detail', kwargs={'pk': product.id})
        })
