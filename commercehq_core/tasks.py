import requests
import time

import simplejson as json

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.cache import cache
from django.template.defaultfilters import truncatewords
from raven.contrib.django.raven_compat.models import client as raven_client

from app.celery import celery_app, CaptureFailure
from shopified_core import utils
from shopified_core import permissions

from .models import (
    CommerceHQStore,
    CommerceHQProduct,
    CommerceHQSupplier
)


@celery_app.task(base=CaptureFailure)
def save_for_later(req_data, user_id):
    start = time.time()

    store = req_data.get('store')
    data = req_data['data']
    variants_mapping = None

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

    if 'product' in req_data:
        # Saved product update
        try:
            product = CommerceHQProduct.objects.get(id=req_data['product'])
            permissions.user_can_edit(user, product)

        except ShopifyProduct.DoesNotExist:
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
            'url': '/product/%d' % product.id,
            'id': product.id,
        }
    }
