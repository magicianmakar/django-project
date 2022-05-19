import json

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from app.celery_base import CaptureFailure, celery_app
from lib.exceptions import capture_exception
from shopified_core import permissions
from shopified_core.utils import get_domain, safe_str

from .models import FBMarketplaceProduct, FBMarketplaceStore, FBMarketplaceSupplier


@celery_app.task(base=CaptureFailure)
def product_save(req_data, user_id):
    store = req_data.get('store')
    data = req_data['data']

    user = User.objects.get(id=user_id)

    # raven_client.extra_context({'store': store, 'product': req_data.get('product'), 'from_extension': ('access_token' in req_data)})

    if store:
        try:
            store = FBMarketplaceStore.objects.get(id=store)
            permissions.user_can_view(user, store)

        except (FBMarketplaceStore.DoesNotExist, ValueError):
            capture_exception()

            return {
                'error': 'Selected store (%s) not found' % (store)
            }
        except PermissionDenied as e:
            return {
                'error': "Store: {}".format(str(e))
            }
    else:
        store = user.profile.get_fb_marketplace_stores().first()

    original_url = json.loads(data).get('original_url')
    if not original_url:
        original_url = req_data.get('original_url')

    try:
        import_store = get_domain(original_url)
    except:
        capture_exception(extra={'original_url': original_url})

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
            product = FBMarketplaceProduct.objects.get(id=req_data['product'])
            permissions.user_can_edit(user, product)

        except FBMarketplaceProduct.DoesNotExist:
            capture_exception()
            return {
                'error': "Product {} does not exist".format(req_data['product'])
            }

        except PermissionDenied as e:
            capture_exception()
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
                'error': "Woohoo! 🎉. You are growing and you've hit your account limit for products. "
                         "Upgrade your plan to keep importing new products"
            }

        try:
            product = FBMarketplaceProduct(store=store, user=user.models_user, notes=req_data.get('notes'))
            product.update_data(data)

            user_supplement_id = json.loads(data).get('user_supplement_id')
            product.user_supplement_id = user_supplement_id

            permissions.user_can_add(user, product)
            product.save()

            store_info = json.loads(data).get('store')

            supplier = FBMarketplaceSupplier.objects.create(
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
            'url': reverse('fb_marketplace:product_detail', kwargs={'pk': product.id}),
            'id': product.id,
        }
    }
