import json
import requests
from tempfile import mktemp
from zipfile import ZipFile

from lib.exceptions import capture_exception
from pusher import Pusher

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.conf import settings
from django.template.defaultfilters import truncatewords
from django.utils.text import slugify
from django.core.cache import cache

from app.celery_base import celery_app, CaptureFailure, retry_countdown
from shopified_core import permissions
from shopified_core import utils

from gearbubble_core.models import GearBubbleStore, GearBubbleProduct, GearBubbleSupplier
from shopified_core.utils import safe_str
from .utils import (
    format_gear_errors,
    get_product_export_data,
    get_product_update_data,
    get_effect_on_current_images,
    OrderListQuery,
    GearOrderUpdater,
)


@celery_app.task(base=CaptureFailure)
def product_save(req_data, user_id):
    User = get_user_model()
    store = req_data.get('store')
    data = req_data['data']
    user = User.objects.get(id=user_id)
    # raven_client.extra_context({'store': store, 'product': req_data.get('product'), 'from_extension': ('access_token' in req_data)})

    if store:
        try:
            store = GearBubbleStore.objects.get(id=store)
            permissions.user_can_view(user, store)
        except (GearBubbleStore.DoesNotExist, ValueError):
            capture_exception()
            return {'error': 'Selected store (%s) not found' % (store)}
        except PermissionDenied as e:
            return {'error': "Store: {}".format(str(e))}
    else:
        store = user.profile.get_gear_stores().first()

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
            product = GearBubbleProduct.objects.get(id=req_data['product'])
            permissions.user_can_edit(user, product)
        except GearBubbleProduct.DoesNotExist:
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
                'error': "Woohoo! ????. You are growing and you've hit your account limit for products. "
                         "Upgrade your plan to keep importing new products"
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
        r = store.request.post(store.get_api_url('private_products'), json=api_data)
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
        capture_exception(extra={'response': response})
        pusher_data['error'] = format_gear_errors(e)

        return store.pusher_trigger('product-export', pusher_data)


@celery_app.task(base=CaptureFailure)
def product_update(product_id, data):
    product = GearBubbleProduct.objects.get(id=product_id)
    product_url = reverse('gear:product_detail', kwargs={'pk': product.id})
    store = product.store
    product.update_data({'type': data.get('type', '')})
    product.save()
    api_url = store.get_api_url('private_products/{}'.format(product.source_id))
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
        capture_exception(extra={'response': response})
        pusher_data['error'] = format_gear_errors(e)

        return store.pusher_trigger('product-update', pusher_data)


@celery_app.task(bind=True, base=CaptureFailure)
def create_image_zip(self, images, product_id):
    from leadgalaxy.utils import aws_s3_upload

    try:
        product = GearBubbleProduct.objects.get(pk=product_id)
        filename = mktemp(suffix='.zip', prefix='{}-'.format(product_id))

        with ZipFile(filename, 'w') as images_zip:
            for i, img_url in enumerate(images):
                image_name = 'image-{}.{}'.format(i + 1, utils.get_fileext_from_url(img_url, fallback='jpg'))
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
        capture_exception()


@celery_app.task(base=CaptureFailure, bind=True)
def order_save_changes(self, data):
    order_id = None
    try:
        updater = GearOrderUpdater()
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
