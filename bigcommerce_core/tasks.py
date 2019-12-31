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

from raven.contrib.django.raven_compat.models import client as raven_client

from app.celery_base import celery_app, CaptureFailure, retry_countdown
from shopified_core import utils
from shopified_core import permissions

from .models import BigCommerceStore, BigCommerceProduct, BigCommerceSupplier
from .utils import (
    format_bigcommerce_errors,
    get_image_url_by_hash,
    add_product_images_to_api_data,
    update_product_api_data,
    update_variants_api_data,
    update_product_images_api_data,
    create_variants_api_data,
    get_latest_order_note,
    find_or_create_category,
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

    raven_client.extra_context({
        'store': store,
        'product': req_data.get('product'),
        'from_extension': ('access_token' in req_data)
    })

    if store:
        try:
            store = BigCommerceStore.objects.get(id=store)
            permissions.user_can_view(user, store)

        except (BigCommerceStore.DoesNotExist, ValueError):
            raven_client.captureException()

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
            product = BigCommerceProduct.objects.get(id=req_data['product'])
            permissions.user_can_edit(user, product)

        except BigCommerceProduct.DoesNotExist:
            raven_client.captureException()
            return {
                'error': "Product {} does not exist".format(req_data['product'])
            }

        except PermissionDenied as e:
            raven_client.captureException()
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
                'error': 'Your current plan allow up to %d saved products, currently you have %d saved products.'
                         % (total_allowed, user_count)
            }

        try:
            product = BigCommerceProduct(store=store, user=user.models_user)
            product.update_data(data)
            permissions.user_can_add(user, product)
            product.save()

            store_info = json.loads(data).get('store')

            supplier = BigCommerceSupplier.objects.create(
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
        product.save()

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
        raven_client.captureException(extra=utils.http_exception_response(e))

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
        api_data = update_product_api_data(api_data, data)
        api_data = update_product_images_api_data(api_data, data)
        api_data['variants'] = update_variants_api_data(api_data.get('variants', []), data.get('variants', []))

        r = store.request.put(
            url=store.get_api_url('v3/catalog/products/%s' % product.source_id),
            json=api_data
        )
        r.raise_for_status()

        product.source_id = r.json()['data']['id']
        product.save()

        store.pusher_trigger('product-update', {
            'success': True,
            'product': product.id,
            'product_url': reverse('bigcommerce:product_detail', kwargs={'pk': product.id})
        })

    except Exception as e:
        raven_client.captureException(extra=utils.http_exception_response(e))

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
        raven_client.captureException()

        product.store.pusher_trigger('images-download', {
            'success': False,
            'product': product_id,
        })


@celery_app.task(base=CaptureFailure)
def get_latest_order_note_task(store_id, order_id):
    store = BigCommerceStore.objects.get(pk=store_id)
    data = {'order_id': order_id}

    try:
        note = get_latest_order_note(store, order_id)
        data['success'] = True
        data['note'] = note
    except Exception:
        raven_client.captureException()
        data['success'] = False

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
                    product_data['inventory_tracking'] = 'variant'
                elif len(product_data.get('variants', [])) == 0 or variant_id < 0:
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
        raven_client.captureException()

        if not self.request.called_directly:
            countdown = retry_countdown('retry_sync_bigcommerce_{}'.format(product_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)
