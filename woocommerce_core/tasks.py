import simplejson as json
import requests
import re

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils.text import slugify
from django.conf import settings
from django.template.defaultfilters import truncatewords

from raven.contrib.django.raven_compat.models import client as raven_client

from unidecode import unidecode

from app.celery import celery_app, CaptureFailure, retry_countdown
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
    get_latest_order_note,
    WooOrderUpdater
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
                product_url=original_url[:512],
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

        if product.source_id and product.store.id == store.id:
            raise ValueError('Product already connected to WooCommerce store.')

        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)

        product.store = store
        product.save()

        saved_data = product.parsed
        saved_data['published'] = saved_data['published'] if publish is None else publish
        api_data = update_product_api_data({}, saved_data, store)
        api_data = add_product_images_to_api_data(api_data, saved_data)
        api_data = add_product_attributes_to_api_data(api_data, saved_data)
        api_data = add_store_tags_to_api_data(api_data, store, saved_data.get('tags', []))

        r = store.get_wcapi(timeout=60).post('products', api_data)
        if not r.ok:
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
            image_id_by_hash = get_image_id_by_hash(product_data)
            variant_list = create_variants_api_data(saved_data, image_id_by_hash)
            path = 'products/{}/variations/batch'.format(product.source_id)
            r = store.get_wcapi(timeout=60).post(path, {'create': variant_list})
            r.raise_for_status()

        store.pusher_trigger('product-export', {
            'success': True,
            'product': product.id,
            'product_url': reverse('woo:product_detail', kwargs={'pk': product.id}),
            'woocommerce_url': product.woocommerce_url
        })

    except ValueError as e:
        store.pusher_trigger('product-export', {
            'success': False,
            'error': str(e),
            'product': product.id,
            'product_url': reverse('woo:product_detail', kwargs={'pk': product.id}),
        })

    except Exception as e:
        raven_client.captureException(extra=utils.http_exception_response(e))

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

        r = store.get_wcapi(timeout=60).put('products/{}'.format(product.source_id), api_data)
        r.raise_for_status()

        product.update_data({'type': data.get('type', '')})
        product.source_id = r.json()['id']
        product.save()

        variants_data = data.get('variants', [])
        if variants_data:
            variants = update_variants_api_data(variants_data)
            path = 'products/%s/variations/batch' % product.source_id
            r = store.get_wcapi(timeout=60).post(path, {'update': variants})
            r.raise_for_status()

        store.pusher_trigger('product-update', {
            'success': True,
            'product': product.id,
            'product_url': reverse('woo:product_detail', kwargs={'pk': product.id})
        })

    except Exception as e:
        raven_client.captureException(extra=utils.http_exception_response(e))

        store.pusher_trigger('product-update', {
            'success': False,
            'error': format_woo_errors(e),
            'product': product.id,
            'product_url': reverse('woo:product_detail', kwargs={'pk': product.id})
        })


@celery_app.task(bind=True, base=CaptureFailure)
def create_image_zip(self, images, product_id):
    from os.path import join as path_join
    from tempfile import mktemp
    from zipfile import ZipFile

    from leadgalaxy.utils import aws_s3_upload

    try:
        product = WooProduct.objects.get(pk=product_id)
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


@celery_app.task(base=CaptureFailure)
def get_latest_order_note_task(store_id, order_id):
    store = WooStore.objects.get(pk=store_id)
    data = {'order_id': order_id}

    try:
        note = get_latest_order_note(store, order_id)
        data['success'] = True
        data['note'] = note
    except Exception:
        raven_client.captureException()
        data['success'] = False

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
        raven_client.captureException(extra=utils.http_exception_response(e))

        if not self.request.called_directly:
            countdown = retry_countdown('retry_ordered_tags_{}'.format(order_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)
