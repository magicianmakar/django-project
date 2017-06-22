import simplejson as json

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse

from raven.contrib.django.raven_compat.models import client as raven_client

from app.celery import celery_app, CaptureFailure
from shopified_core import utils
from shopified_core import permissions

from .models import WooStore, WooProduct, WooSupplier
from .utils import (
    format_woo_errors,
    get_image_id_by_hash,
    add_product_images_to_api_data,
    add_product_attributes_to_api_data,
    add_store_tags_to_api_data,
    update_product_api_data,
    update_variants_api_data,
    update_product_images_api_data,
    create_variants_api_data,
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

            store_info = json.loads(data).get('store')

            supplier = WooSupplier.objects.create(
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
        saved_data['published'] = saved_data['published'] if publish is None else publish
        api_data = update_product_api_data({}, saved_data)
        api_data = add_product_images_to_api_data(api_data, saved_data)
        api_data = add_product_attributes_to_api_data(api_data, saved_data)
        api_data = add_store_tags_to_api_data(api_data, store, saved_data.get('tags', []))

        r = store.wcapi.post('products', api_data)
        r.raise_for_status()

        product_data = r.json()
        product.source_id = product_data['id']
        product.save()

        if saved_data.get('variants', []):
            image_id_by_hash = get_image_id_by_hash(product_data)
            variant_list = create_variants_api_data(saved_data, image_id_by_hash)
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
        api_data = product.retrieve()
        api_data = update_product_api_data(api_data, data)
        api_data = add_store_tags_to_api_data(api_data, store, data.get('tags', []))
        api_data = update_product_images_api_data(api_data, data)

        r = store.wcapi.put('products/{}'.format(product.source_id), api_data)
        r.raise_for_status()

        product.source_id = r.json()['id']
        product.save()

        variants_data = data.get('variants', [])
        if variants_data:
            variants = update_variants_api_data(variants_data)
            path = 'products/%s/variations/batch' % product.source_id
            r = store.wcapi.post(path, {'update': variants})
            r.raise_for_status()

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
