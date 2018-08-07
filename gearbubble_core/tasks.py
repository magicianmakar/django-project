import json
import requests
from unidecode import unidecode

from raven.contrib.django.raven_compat.models import client as raven_client
from pusher import Pusher

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.conf import settings
from django.utils.text import slugify
from django.core.cache import cache

from app.celery import celery_app, CaptureFailure
from shopified_core import permissions
from shopified_core import utils

from gearbubble_core.models import GearBubbleStore, GearBubbleProduct, GearBubbleSupplier
from .utils import (
    get_api_url,
    format_gear_errors,
    get_product_export_data,
    get_product_update_data,
    OrderListQuery,
    get_effect_on_current_images
)


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
            store = GearBubbleStore.objects.get(id=store)
            permissions.user_can_view(user, store)
        except (GearBubbleStore.DoesNotExist, ValueError):
            raven_client.captureException()
            return {'error': 'Selected store (%s) not found' % (store)}
        except PermissionDenied as e:
            return {'error': "Store: {}".format(e.message)}
    else:
        store = user.profile.get_gear_stores().first()

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
            product = GearBubbleProduct.objects.get(id=req_data['product'])
            permissions.user_can_edit(user, product)
        except GearBubbleProduct.DoesNotExist:
            raven_client.captureException()
            return {'error': "Product {} does not exist".format(req_data['product'])}
        except PermissionDenied as e:
            raven_client.captureException()
            return {'error': "Product: {}".format(e.message)}

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
            product = GearBubbleProduct(store=store, user=user.models_user)
            product.update_data(data)
            permissions.user_can_add(user, product)
            product.save()

            store_info = json.loads(data).get('store')

            supplier = GearBubbleSupplier.objects.create(
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
            'url': reverse('gear:product_detail', kwargs={'pk': product.id}),
            'id': product.id,
        }
    }


@celery_app.task(base=CaptureFailure)
def product_export(store_id, product_id, user_id, publish=None):
    user = get_user_model().objects.get(id=user_id)
    store = GearBubbleStore.objects.get(id=store_id)
    product = GearBubbleProduct.objects.get(id=product_id)
    product_url = reverse('gear:product_detail', kwargs={'pk': product.id})
    pusher_data = {'success': False, 'product': product.id, 'product_url': product_url}
    images = product.parsed.get('images', [])

    if product.source_id and product.store.id == store.id:
        pusher_data['error'] = 'Product already connected to GearBubble store.'

        return store.pusher_trigger('product-export', pusher_data)

    try:
        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)
        vendor_product = get_product_export_data(product)
        api_data = {'vendor_product': vendor_product}
        r = store.request.post(get_api_url('private_products'), json=api_data)
        r.raise_for_status()
        product.store = store
        product_data = r.json()['product']
        product.source_id = product_data['id']
        product.source_slug = product_data['slug']
        product.update_data({'source_id': product_data['id']})
        product.update_data({'source_slug': product_data['slug']})
        product.update_data({'original_images': images[:]})
        product.save()
        pusher_data['success'] = True

        return store.pusher_trigger('product-export', pusher_data)

    except Exception as e:
        response = e.response.text if hasattr(e, 'response') else ''
        raven_client.captureException(extra={'response': response})
        pusher_data['error'] = format_gear_errors(e)

        return store.pusher_trigger('product-export', pusher_data)


@celery_app.task(base=CaptureFailure)
def product_update(product_id, data):
    product = GearBubbleProduct.objects.get(id=product_id)
    product_url = reverse('gear:product_detail', kwargs={'pk': product.id})
    store = product.store
    product.update_data({'type': data.get('type', '')})
    product.save()
    api_url = get_api_url('private_products/{}'.format(product.source_id))
    pusher_data = {'success': False, 'product': product.id, 'product_url': product_url}

    try:
        gearbubble_product = get_product_update_data(product, data)
        effect_on_current_images = get_effect_on_current_images(product, data)

        if effect_on_current_images == 'change':
            # Deletes all current images so that they can be replaced
            r = store.request.put(api_url, json={'product': {'id': product.source_id, 'images': []}})
            r.raise_for_status()

        r = store.request.put(api_url, json={'product': gearbubble_product})
        r.raise_for_status()
        pusher_data['success'] = True

        return store.pusher_trigger('product-update', pusher_data)

    except Exception as e:
        response = e.response.text if hasattr(e, 'response') else ''
        raven_client.captureException(extra={'response': response})
        pusher_data['error'] = format_gear_errors(e)

        return store.pusher_trigger('product-update', pusher_data)


@celery_app.task(bind=True, base=CaptureFailure)
def create_image_zip(self, images, product_id):
    from os.path import join as path_join
    from tempfile import mktemp
    from zipfile import ZipFile

    from leadgalaxy.utils import aws_s3_upload

    try:
        product = GearBubbleProduct.objects.get(pk=product_id)
        filename = mktemp(suffix='.zip', prefix='{}-'.format(product_id))

        with ZipFile(filename, 'w') as images_zip:
            for i, img_url in enumerate(images):
                image_name = u'image-{}.{}'.format(i + 1, utils.get_fileext_from_url(img_url, fallback='jpg'))
                images_zip.writestr(image_name, requests.get(img_url, verify=not settings.DEBUG).content)

        s3_path = path_join('product-downloads', str(product.id), u'{}.zip'.format(slugify(unidecode(product.title))))
        url = aws_s3_upload(s3_path, input_filename=filename)

        product.store.pusher_trigger('images-download', {
            'success': True,
            'product': product_id,
            'url': url
        })
    except Exception:
        raven_client.captureException()

        product.store.pusher_trigger('images-download', {
            'success': False,
            'product': product_id,
        })


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def calculate_user_statistics(self, user_id):
    try:
        User = get_user_model()
        user = User.objects.get(id=user_id)
        stores = user.profile.get_gear_stores()

        stores_data = []
        for store in stores:
            order_query = OrderListQuery(store, {'fulfillment_status': 'unshipped', 'status': 'paid'})

            stores_data.append({
                'id': store.id,
                'products_connected': store.connected_count(),
                'products_saved': store.saved_count(),
                'pending_orders': order_query.count(),
            })

        cache.set('gear_user_statistics_{}'.format(user_id), stores_data, timeout=3600)

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger("user_{}".format(user_id), 'gear-user-statistics-calculated', {'task': self.request.id})

    except:
        raven_client.captureException()
