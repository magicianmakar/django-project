import simplejson as json

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.utils.text import slugify

import requests
from raven.contrib.django.raven_compat.models import client as raven_client

from unidecode import unidecode

from app.celery import celery_app, CaptureFailure
from shopified_core import utils
from shopified_core import permissions

from .models import (
    CommerceHQStore,
    CommerceHQProduct,
    CommerceHQSupplier
)


# TODO: move to .utils
def format_chq_errors(e):
    if not hasattr(e, 'response') or e.response.status_code != 422:
        return 'Server Error'

    errors = e.response.json().get('errors')

    if isinstance(errors, basestring):
        return errors

    msg = []
    for k, v in errors.items():
        if type(v) is list:
            error = u','.join(v)
        else:
            error = v

        if k == 'base':
            msg.append(error)
        else:
            msg.append(u'{}: {}'.format(k, error))

    return u' | '.join(msg)


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
            store = CommerceHQStore.objects.get(id=store)
            permissions.user_can_view(user, store)

        except (CommerceHQStore.DoesNotExist, ValueError):
            raven_client.captureException()

            return {
                'error': 'Selected store (%s) not found' % (store)
            }
        except PermissionDenied as e:
            return {
                'error': "Store: {}".format(e.message)
            }

    original_url = json.loads(data).get('original_url')
    if not original_url:
        original_url = req_data.get('original_url')

    # if not original_url:  # Could be sent from the web app
    #     try:
    #         product = ShopifyProduct.objects.get(id=req_data.get('product'))
    #         permissions.user_can_edit(user, product)

    #         original_url = product.get_original_info().get('url', '')

    #     except ShopifyProduct.DoesNotExist:
    #         original_url = ''

    #     except PermissionDenied as e:
    #         return {
    #             'error': "Product: {}".format(e.message)
    #         }
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
            try:
                if 'free' not in user.profile.plan.title.lower():
                    print u'ERROR: STORE PERMISSION FOR [{}] [{}] [{}] User: {}'.format(
                        import_store, original_url, user.profile.plan.title, user.username)
            except:
                pass

            return {
                'error': 'Importing from this store ({}) is not included in your current plan.'.format(import_store)
            }

    if req_data.get('product'):
        # Saved product update
        try:
            product = CommerceHQProduct.objects.get(id=req_data['product'])
            permissions.user_can_edit(user, product)

        except CommerceHQProduct.DoesNotExist:
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
            product = CommerceHQProduct(store=store, user=user.models_user, notes=req_data.get('notes'))
            product.update_data(data)

            permissions.user_can_add(user, product)

            product.save()

            store_info = json.loads(data).get('store')
            supplier = CommerceHQSupplier.objects.create(
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
            'url': reverse('chq:product_detail', kwargs={'pk': product.id}),
            'id': product.id,
        }
    }


@celery_app.task(base=CaptureFailure)
def product_export(store_id, product_id, user_id):
    try:
        user = User.objects.get(id=user_id)

        store = CommerceHQStore.objects.get(id=store_id)
        product = CommerceHQProduct.objects.get(id=product_id)

        permissions.user_can_view(user, store)
        permissions.user_can_edit(user, product)

        product.store = store
        product.save()

        p = product.parsed

        images = []
        variants_thmbs = {}
        thumbs_idx = {}
        thumbs_uploads = {}

        for h, var in p['variants_images'].items():
            for idx, img in enumerate(p['images']):
                if utils.hash_url_filename(img) == h:
                    variants_thmbs[var] = img
                    thumbs_idx[idx] = var

        for idx, img in enumerate(p['images']):
            is_thumb = idx in thumbs_idx

            store.pusher_trigger('product-export', {
                'product': product.id,
                'progress': 'Uploading Images ({}%)'.format(((idx + 1) * 100 / len(p['images'])) - 1),
            })

            r = store.request.post(
                url=store.get_api_url('files'),
                files={'files': (
                    utils.get_filename_from_url(img), requests.get(img).content, 'image/png', {'Expires': '0'})
                },
                data={
                    'type': ('thumbnails' if is_thumb else 'product_images')
                }
            )

            r.raise_for_status()

            for j in r.json():
                upload_id = j['id']
                if is_thumb:
                    if idx in thumbs_idx:
                        thumbs_uploads[thumbs_idx[idx]] = upload_id
                else:
                    images.append(j['id'])

        is_multi = len(p['variants']) > 0
        if p['weight_unit'] == 'g':
            weight = utils.safeFloat(p['weight'], 0.0) / 1000.0
        elif p['weight_unit'] == 'lb':
            weight = utils.safeFloat(p['weight'], 0.0) * 0.45359237
        elif p['weight_unit'] == 'oz':
            weight = utils.safeFloat(p['weight'], 0.0) * 0.0283495
        else:
            weight = utils.safeFloat(p['weight'], 0.0)

        weight = '{:.02f}'.format(weight)

        api_data = {
            'is_draft': not p['published'],
            'title': p['title'],
            'is_multi': is_multi,
            'textareas': [{
                'active': True,
                'text': p['description'],
                'name': 'Description'
            }],
            'images': images,

            # 'seo_url': slugify(p['title']),
            # 'seo_title': p['title'],

            'vendor': p['vendor'],
            'tags': p['tags'].split(','),
            'type': p['type'],
            'shipping_weight': weight,

            'price': utils.safeFloat(p['price']),
            'compare_price': utils.safeFloat(p['compare_at_price'], ''),

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

                api_data['options'].append(option)

            vars_list = []
            for v in p['variants']:
                vars_list.append(v['values'])

            vars_list = all_possible_cases(vars_list)

            for idx, variants in enumerate(vars_list):
                if type(variants) is list:
                    title = ' / '.join(variants)
                else:
                    title = variants
                    variants = [variants]

                sku = []
                for v in variants:
                    if v in p.get('variants_sku', []):
                        sku.append(p['variants_sku'][v])

                var_info = {
                    'default': idx == 0,
                    'title': title,
                    'price': utils.safeFloat(p['price']),
                    'compare_price': utils.safeFloat(p['compare_at_price'], ''),
                    'shipping_weight': weight,
                    'variant': variants,
                    'sku': ';'.join(sku),
                }

                api_data['variants'].append(var_info)

        rep = store.request.post(
            url=store.get_api_url('products'),
            json=api_data
        )

        rep.raise_for_status()

        product.source_id = rep.json()['id']
        product.save()

        store.pusher_trigger('product-export', {
            'success': True,
            'product': product.id,
            'product_url': reverse('chq:product_detail', kwargs={'pk': product.id}),
            'commercehq_url': product.commercehq_url
        })

    except Exception as e:
        raven_client.captureException(extra={
            'response': e.response.text if hasattr(e, 'response') else ''
        })

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
        p['tags'] = data['tags'].split(',')
        p['vendor'] = data['vendor']
        p['is_draft'] = not data['published']
        p['price'] = data['price']
        p['compare_price'] = data['compare_price']

        if 'weight_unit' in p and 'weight' in p:
            if p['weight_unit'] == 'g':
                weight = utils.safeFloat(p['weight'], 0.0) / 1000.0
            elif p['weight_unit'] == 'lb':
                weight = utils.safeFloat(p['weight'], 0.0) * 0.45359237
            elif p['weight_unit'] == 'oz':
                weight = utils.safeFloat(p['weight'], 0.0) * 0.0283495
            else:
                weight = utils.safeFloat(p['weight'], 0.0)

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

        images_need_upload = []
        for img in data['images']:
            if img not in [j['path'] for j in p['images']]:
                images_need_upload.append(img)

        for idx, img in enumerate(images_need_upload):
            store.pusher_trigger('product-update', {
                'product': product.id,
                'progress': 'Uploading Images ({}%)'.format(((idx + 1) * 100 / len(images_need_upload)) - 1),
            })

            r = store.request.post(
                url=store.get_api_url('files'),
                files={'files': (
                    utils.get_filename_from_url(img), requests.get(img).content, 'image/png', {'Expires': '0'})
                },
                data={
                    'type': 'product_images'
                }
            )

            r.raise_for_status()

            for j in r.json():
                p['images'].append(j['id'])

        for i, image in enumerate(p['images']):
            if type(image) is int:
                continue

            if 'id' in image:
                p['images'][i] = image['id']

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
        raven_client.captureException(extra={
            'response': e.response.text if hasattr(e, 'response') else ''
        })

        store.pusher_trigger('product-update', {
            'success': False,
            'error': format_chq_errors(e),
            'product': product.id,
            'product_url': reverse('chq:product_detail', kwargs={'pk': product.id})
        })


def all_possible_cases(arr, top=True):
    sep = '_'.join([str(i) for i in range(10)])

    if (len(arr) == 0):
        return []
    elif (len(arr) == 1):
        return arr[0]
    else:
        result = []
        allCasesOfRest = all_possible_cases(arr[1:], False)
        for c in allCasesOfRest:
            for i in arr[0]:
                result.append('{}{}{}'.format(i, sep, c))

        return map(lambda k: k.split(sep), result) if top else result

@celery_app.task(bind=True, base=CaptureFailure)
def create_image_zip(self, images, product_id):
    from os.path import join as path_join
    from tempfile import mktemp
    from zipfile import ZipFile

    from leadgalaxy.utils import aws_s3_upload

    try:
        product = CommerceHQProduct.objects.get(pk=product_id)
        filename = mktemp(suffix='.zip', prefix='{}-'.format(product_id))

        with ZipFile(filename, 'w') as images_zip:
            for i, img_url in enumerate(images):
                image_name = u'image-{}.{}'.format(i + 1, utils.get_fileext_from_url(img_url, fallback='jpg'))
                images_zip.writestr(image_name, requests.get(img_url).content)

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
