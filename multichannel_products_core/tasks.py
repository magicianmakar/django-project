import simplejson as json

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from app.celery_base import CaptureFailure, celery_app
from lib.exceptions import capture_exception
from shopified_core import permissions
from shopified_core.utils import get_domain, safe_str

from .models import MasterProduct, MasterProductSupplier


@celery_app.task(base=CaptureFailure)
def product_save(req_data, user_id, is_extension=True):
    if not is_extension:
        data = req_data.get('data', {})
        notes = json.loads(data).get('notes')
    else:
        data = req_data.get('data', {})
        notes = req_data.get('notes', '')

    user = User.objects.get(id=user_id)

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
            product = MasterProduct.objects.get(id=req_data['product'])
            permissions.user_can_edit(user, product)

        except MasterProduct.DoesNotExist:
            capture_exception()
            return {
                'error': "Product {} does not exist".format(req_data['product'])
            }

        except PermissionDenied as e:
            capture_exception()
            return {
                'error': "Product: {}".format(str(e))
            }

        product_data = json.loads(data)
        product.title = product_data.get('title')
        product.description = product_data.get('description')
        product.price = float(product_data.get('price')) if product_data.get('price') else None
        product.compare_at_price = (float(product_data.get('compare_at_price'))
                                    if product_data.get('compare_at_price') else None)
        product.images = json.dumps(product_data.get('images', []))
        product.product_type = product_data.get('type')
        product.tags = product_data.get('tags')
        product.notes = product.notes if notes is None else notes
        product.original_url = product_data.get('original_url')
        product.vendor = product_data.get('vendor')
        product.published = product_data.get('published')
        variants_config = json.loads(product.variants_config)
        for field in ['variants_images', 'variants_sku', 'variants', 'variants_info']:
            if product_data.get(field):
                variants_config[field] = product_data.get(field)
        product.variants_config = json.dumps(variants_config)

        if is_extension:
            product.update_extension_data(data)

        product.save()

    else:  # New product to save

        try:
            product_data = json.loads(data)
            product = MasterProduct(
                user=user.models_user,
                title=product_data.get('title'),
                description=product_data.get('description'),
                price=product_data.get('price'),
                compare_at_price=product_data.get('compare_at_price') if product_data.get('compare_at_price') else None,
                images=json.dumps(product_data.get('images', [])),
                product_type=product_data.get('type') or product_data.get('product_type'),
                tags=product_data.get('tags'),
                notes=notes,
                original_url=product_data.get('original_url'),
                vendor=product_data.get('vendor'),
                published=product_data.get('published'),
                variants_config=json.dumps({
                    'variants_images': product_data.get('variants_images'),
                    'variants_sku': product_data.get('variants_sku'),
                    'variants': product_data.get('variants'),
                    'variants_info': product_data.get('variants_info'),
                })
            )
            if is_extension:
                product.update_extension_data(data)

            permissions.user_can_add(user, product)
            product.save()

            store_info = product_data.get('store')
            supplier = MasterProductSupplier.objects.create(
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
            'url': reverse('multichannel:product_detail', kwargs={'pk': product.id}),
            'id': product.id,
        }
    }
