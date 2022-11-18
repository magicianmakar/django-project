import arrow
import requests
import time
import tempfile
import zipfile
import re
import os.path

import simplejson as json
from pusher import Pusher
from simplejson import JSONDecodeError
from datetime import timedelta

from django.conf import settings
from django.db import transaction, IntegrityError
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.cache import cache, caches
from django.template.defaultfilters import truncatewords
from django.utils import timezone
from django.utils.text import slugify

from lib.exceptions import capture_exception, capture_message
from app.celery_base import celery_app, CaptureFailure, retry_countdown, api_exceed_limits_countdown
from multichannel_products_core.utils import rewrite_master_variants_map
from shopified_core import permissions
from shopified_core.paginators import SimplePaginator
from shopified_core.utils import (
    safe_int,
    app_link,
    get_domain,
    random_hash,
    hash_list,
    get_fileext_from_url,
    http_exception_response,
    http_excption_status_code,
    delete_model_from_db,
    normalize_product_title,
    safe_str,
    ALIEXPRESS_REJECTED_STATUS
)

from leadgalaxy.models import (
    ProductSupplier,
    ShopifyBoard,
    ShopifyOrderTrack,
    ShopifyProduct,
    ShopifyStore,
    UserProfile,
)
from supplements.models import UserSupplement
from leadgalaxy import utils
from leadgalaxy.shopify import ShopifyAPI

from shopified_core.utils import (
    update_product_data_images,
)
from shopify_orders import utils as order_utils

from product_alerts.models import ProductChange
from product_alerts.managers import ProductChangeManager
from product_alerts.utils import (
    get_supplier_variants,
    variant_index_from_supplier_sku
)

from product_feed.feed import (
    generate_product_feed,
    generate_chq_product_feed,
    generate_woo_product_feed,
    generate_gear_product_feed,
    generate_gkart_product_feed,
    generate_bigcommerce_product_feed,
)
from product_feed.models import (
    FeedStatus,
    CommerceHQFeedStatus,
    WooFeedStatus,
    GearBubbleFeedStatus,
    GrooveKartFeedStatus,
    BigCommerceFeedStatus,
)

from order_exports.models import OrderExport
from order_exports.utils import ShopifyOrderExport, ShopifyTrackOrderExport
from metrics.statuspage import record_import_metric
from shopify_orders.models import ShopifyOrder, ShopifyOrderRevenue, ShopifyOrderRisk
from woocommerce_core.models import (
    WooStore,
    WooProduct,
    WooBoard,
    WooOrderTrack,
)


@celery_app.task(base=CaptureFailure)
def export_product(req_data, target, user_id):
    start = time.time()

    store = req_data.get('store') if safe_int(req_data.get('store')) > 0 else None
    data = req_data['data']
    parsed_data = json.loads(req_data['data'])
    original_data = req_data.get('original', '')
    variants_mapping = None

    user = User.objects.get(id=user_id)

    # raven_client.user_context({'id': user.id, 'username': user.username, 'email': user.email})
    # raven_client.extra_context({'target': target, 'store': store, 'product': req_data.get('product'), 'from_extension': ('access_token' in req_data)}) # noqa

    if store or target != 'save-for-later':
        try:
            store = ShopifyStore.objects.get(id=store)
            permissions.user_can_view(user, store)

        except (ShopifyStore.DoesNotExist, ValueError):
            capture_exception()

            return {
                'error': 'Selected store (%s) not found' % (store)
            }
        except PermissionDenied as e:
            return {
                'error': "Store: {}".format(str(e))
            }

    original_url = parsed_data.get('original_url')
    if not original_url:
        original_url = req_data.get('original_url')

    if not original_url:  # Could be sent from the web app
        try:
            product = ShopifyProduct.objects.get(id=req_data.get('product'))
            try:
                permissions.user_can_edit(user, product)
            except PermissionDenied:
                if not (product.store and user.is_subuser and product.store.user == user.models_user):
                    raise

            original_url = product.get_original_info().get('url', '')

        except ShopifyProduct.DoesNotExist:
            original_url = ''

        except PermissionDenied as e:
            return {
                'error': "Product: {}".format(str(e))
            }
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

    if target == 'shopify' or target == 'shopify-update':
        try:
            if target == 'shopify-update':
                product = ShopifyProduct.objects.get(id=req_data['product'])
                permissions.user_can_edit(user, product)

                parsed_data = utils.link_variants_to_new_images(product, parsed_data, req_data)

                api_data = parsed_data
                api_data['product']['id'] = product.get_shopify_id()

                update_endpoint = store.api('products', product.get_shopify_id())
                r = requests.put(update_endpoint, json=api_data)

                if r.ok:
                    try:
                        if product.master_product:
                            # Link images with variants
                            mapped = utils.shopify_link_images(store, r.json()['product'])
                            if mapped:
                                r = mapped
                        shopify_images = r.json()['product'].get('images', [])
                        product_images = api_data['product'].get('images', [])
                        if len(product_images) == len(shopify_images):
                            for i, image in enumerate(product_images):
                                if image.get('src'):
                                    update_product_data_images(product, image['src'], shopify_images[i]['src'])
                    except:
                        capture_exception(level='warning')

                del api_data
            else:
                endpoint = store.api('products')
                api_data = parsed_data

                if api_data['product'].get('variants') and len(api_data['product']['variants']) > 100:
                    api_data['product']['variants'] = api_data['product']['variants'][:100]

                # Duplicated product variants
                duplicate_parent_variants(req_data, api_data)

                if user.get_config('randomize_image_names') and api_data['product'].get('images'):
                    for i, image in enumerate(api_data['product']['images']):
                        if image.get('src') and not image.get('filename'):
                            path, ext = os.path.splitext(image.get('src'))
                            api_data['product']['images'][i]['filename'] = '{}{}'.format(random_hash(), ext)

                if user.id == 43981 and api_data['product'].get('body_html'):
                    api_data['product']['body_html'] = re.sub(r'<(/?)i( [^>]+)?>', r'<\1em\2>', api_data['product']['body_html'])

                # Separate images and merge them later
                remaining_images = []
                max_images_chunk = 50
                if len(api_data['product']['images']) > max_images_chunk:
                    remaining_images = api_data['product']['images'][max_images_chunk:]
                    api_data['product']['images'] = api_data['product']['images'][:max_images_chunk]

                api_data['product']['title'] = normalize_product_title(api_data['product']['title'])

                r = requests.post(endpoint, json=api_data)

                # Shopify can take too long to process each image
                if len(remaining_images) > 0 and 'product' in r.json():
                    created_product = r.json()['product']
                    update_endpoint = store.api('products', created_product['id'])
                    i = 0
                    for chunk in range(0, len(remaining_images), max_images_chunk):
                        i += 1
                        if 'product' in r.json():
                            created_product = r.json()['product']

                        saved_images = [{'id': i['id']} for i in created_product.get('images', [])]
                        r = requests.put(update_endpoint, json={'product': {
                            'id': created_product['id'],
                            'images': saved_images + remaining_images[chunk:chunk + max_images_chunk]
                        }})

                    api_data['product']['images'] += remaining_images

                if 'product' in r.json():
                    product_to_map = r.json()['product']
                    shopify_images = product_to_map.get('images', [])

                    try:
                        if not product_to_map.get('images') and api_data['product'].get('images'):
                            images_fix_data = {
                                'product': {
                                    'id': product_to_map['id'],
                                    'images': api_data['product']['images']
                                }
                            }

                            try:
                                rep = requests.put(
                                    url=store.api('products', product_to_map['id']),
                                    json=images_fix_data
                                )
                                rep.raise_for_status()
                                shopify_images = rep.json()['product'].get('images', [])
                            except:
                                capture_exception(level='warning')

                        # Variant mapping
                        variants_mapping = utils.get_mapping_from_product(product_to_map)

                        # Duplicated product variant mapping
                        duplicate_product_mapping(req_data, product_to_map, variants_mapping)

                        variants_mapping = json.dumps(variants_mapping)

                        # Link images with variants
                        mapped = utils.shopify_link_images(store, product_to_map)
                        if mapped:
                            r = mapped
                    except Exception:
                        capture_exception()

                del api_data

            if 'product' not in r.json():
                rep = r.json()

                shopify_error = utils.format_shopify_error(rep)

                if 'Invalid API key or access token' in shopify_error:
                    print('SHOPIFY EXPORT: {} - Store: {} - Link: {}'.format(
                        shopify_error, store, store.api('products')
                    ))
                else:
                    print('SHOPIFY EXPORT: {} - Store: {} - Product: {}'.format(
                        shopify_error, store, req_data.get('product')))

                if 'requires write_products scope' in shopify_error:
                    return {'error': ('Shopify Error: {}\n\n'
                                      'Please follow this instructions to resolve this issue:\n{}'
                                      ).format(shopify_error, app_link('pages/view/15'))}
                elif 'handle: has already been taken' in shopify_error:
                    return {'error': ('Shopify Error: {}\n\n'
                                      'Please Change your product title by adding or removing one or more words'
                                      ).format(shopify_error)}
                elif 'Exceeded maximum number of variants allowed' in shopify_error:
                    return {'error': ('Shopify Error: {}\n\n'
                                      'Please reduce the number of variants to 100 or less by '
                                      'removing some variant choices to meet Shopify\'s requirements.'
                                      ).format(shopify_error)}
                else:
                    return {'error': 'Shopify Error: {}'.format(shopify_error)}

        except (JSONDecodeError, requests.exceptions.ConnectTimeout):
            capture_exception(extra={
                'rep': r.text
            })

            return {'error': 'Shopify API is not available, please try again.'}

        except ShopifyProduct.DoesNotExist:
            capture_exception()
            return {
                'error': "Product {} does not exist".format(req_data.get('product'))
            }

        except PermissionDenied as e:
            capture_exception()
            return {
                'error': "Product: {}".format(str(e))
            }

        except:
            capture_exception()
            print('WARNING: SHOPIFY EXPORT EXCEPTION:')

            return {'error': 'Shopify API Error'}

        pid = r.json()['product']['id']
        url = store.get_link('/admin/products/{}'.format(pid))

        if target == 'shopify':
            if 'product' in req_data:
                try:
                    product = ShopifyProduct.objects.get(id=req_data['product'])
                    permissions.user_can_edit(user, product)

                    original_url = product.get_original_info().get('url', '')

                    product.shopify_id = pid
                    product.store = store

                    if not product.default_supplier:
                        supplier = product.get_supplier_info()
                        product.default_supplier = ProductSupplier.objects.create(
                            store=store,
                            product=product,
                            product_url=safe_str(original_url)[:512],
                            supplier_name=supplier.get('name') if supplier else '',
                            supplier_url=supplier.get('url') if supplier else '',
                            variants_map=variants_mapping,
                            is_default=True
                        )
                    else:
                        product.default_supplier.variants_map = variants_mapping
                        product.default_supplier.save()

                    if product.title == 'Importing...' and 'product' in parsed_data:
                        old_product_data = json.loads(product.data)
                        old_product_data['title'] = parsed_data['product']['title']
                        product.data = json.dumps(old_product_data)

                    product.save()

                    # Initial Products Inventory Sync
                    if user.models_user.get_config('initial_inventory_sync', True):

                        # Add countdown to not exceed Shopify API limits if this export is started by Bulk Export
                        if req_data.get('b'):
                            countdown_key = 'sync_shopify_product_quantities_countdown_{}'.format(store.id)
                            countdown_quantities = api_exceed_limits_countdown(countdown_key)
                        else:
                            countdown_quantities = 0

                        sync_shopify_product_quantities.apply_async(args=[product.id], countdown=countdown_quantities)

                except ShopifyProduct.DoesNotExist:
                    capture_exception()
                    return {
                        'error': "Product {} does not exist".format(req_data['product'])
                    }

                except PermissionDenied as e:
                    capture_exception()
                    return {
                        'error': "Product: {}".format(str(e))
                    }
            else:
                product = None
        else:
            pass

        product.update_data(data)
        product.save()

    elif target == 'save-for-later':  # save for later
        if 'product' in req_data:
            # Saved product update
            try:
                product = ShopifyProduct.objects.get(id=req_data['product'])

                try:
                    permissions.user_can_edit(user, product)
                except PermissionDenied:
                    if not (product.store and user.is_subuser and product.store.user == user.models_user):
                        raise

            except ShopifyProduct.DoesNotExist:
                capture_exception()
                return {
                    'error': "Product {} does not exist".format(req_data['product'])
                }

            except PermissionDenied as e:
                capture_exception()
                return {
                    'error': "Product: {}".format(str(e))
                }

            product.update_data(json.loads(data).get('product') or data)
            product.store = store

            rewrite_master_variants_map(product)
            product.save()

            boards = parsed_data.get('boards', [])
            if boards:
                utils.attach_boards_with_product(user, product, boards)

        else:  # New product to save

            can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)
            if not can_add:
                return {
                    'error': "Woohoo! 🎉. You are growing and you've hit your account limit for products. "
                             "Upgrade your plan to keep importing new products"

                }

            is_active = req_data.get('activate', True)

            try:
                product = ShopifyProduct(store=store, user=user.models_user, notes=req_data.get('notes', ''), is_active=is_active)
                product.update_data(data)
                product.set_original_data(original_data, commit=False)

                user_supplement_id = json.loads(data).get('user_supplement_id')
                product.user_supplement_id = user_supplement_id

                permissions.user_can_add(user, product)

                product.save()

                boards = parsed_data.get('boards', [])
                if boards:
                    utils.attach_boards_with_product(user, product, boards)

                supplier_info = product.get_supplier_info()
                if supplier_info:
                    supplier = ProductSupplier.objects.create(
                        store=store,
                        product=product,
                        product_url=safe_str(original_url)[:512],
                        supplier_name=supplier_info.get('name') if supplier_info else '',
                        supplier_url=supplier_info.get('url') if supplier_info else '',
                        is_default=True
                    )

                    product.set_default_supplier(supplier, commit=True)

            except PermissionDenied as e:
                capture_exception()
                return {
                    'error': "Add Product: {}".format(str(e))
                }

        utils.smart_board_by_product(user.models_user, product)

        url = '/product/%d' % product.id
        pid = product.id
    else:
        return {
            'error': 'Unknown target {}'.format(target)
        }

    if target == 'shopify':
        try:
            record_import_metric(time.time() - start)
        except:
            capture_exception(level='warning')

    del parsed_data
    del req_data
    del original_data

    return {
        'product': {
            'url': url,
            'id': pid,
        },
        'target': target
    }


def duplicate_parent_variants(req_data, api_data):
    try:
        if not req_data.get('product'):
            return

        product = ShopifyProduct.objects.get(id=req_data['product'])
        parent = product.parent_product
        if parent and parent.shopify_id and parent.store.is_active and product.default_supplier.variants_map:
            parent_shopify_product = cache.get('shopify_product_%s' % parent.shopify_id)
            if parent_shopify_product is None:
                parent_shopify_product = utils.get_shopify_product(parent.store, parent.shopify_id)
                cache.set('shopify_product_%s' % parent.shopify_id, parent_shopify_product, timeout=60)

            if parent_shopify_product:
                for variant in api_data['product']['variants']:
                    for parent_variant in parent_shopify_product['variants']:
                        if parent_variant.get('price') is not None:
                            match = True
                            for option in ['option1', 'option2', 'option3']:
                                if variant.get(option) != parent_variant.get(option):
                                    match = False
                                    break
                            if match:
                                variant['price'] = parent_variant['price']
    except:
        capture_exception(level='warning')


def duplicate_product_mapping(req_data, product_to_map, variants_mapping):
    try:
        if not req_data.get('product'):
            return

        product = ShopifyProduct.objects.get(id=req_data['product'])
        parent = product.parent_product
        if parent and parent.shopify_id and parent.store.is_active and product.default_supplier.variants_map:
            parent_shopify_product = cache.get('shopify_product_%s' % parent.shopify_id)
            if parent_shopify_product is None:
                parent_shopify_product = utils.get_shopify_product(parent.store, parent.shopify_id)
                cache.set('shopify_product_%s' % parent.shopify_id, parent_shopify_product, timeout=60)

            if parent_shopify_product:
                parent_variants_mapping = json.loads(product.default_supplier.variants_map)
                for variant in product_to_map['variants']:
                    for parent_variant in parent_shopify_product['variants']:
                        if parent_variants_mapping.get(str(parent_variant['id'])) is not None:
                            match = True
                            for option in ['option1', 'option2', 'option3']:
                                if variant.get(option) != parent_variant.get(option):
                                    match = False
                                    break
                            if match:
                                variants_mapping[str(variant['id'])] = parent_variants_mapping.get(
                                    str(parent_variant['id']))
    except ShopifyProduct.DoesNotExist:
        return
    except:
        capture_exception(level='warning')


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def sync_shopify_product_quantities(self, product_id):
    try:
        product = ShopifyProduct.objects.get(pk=product_id)
        product_data = utils.get_shopify_product(product.store, product.shopify_id)

        if not product.default_supplier:
            return

        if product.default_supplier.supplier_type() == 'pls':
            mapping_config = product.get_mapping_config()
            supplier = ''
            if mapping_config:
                supplier = mapping_config['supplier']
            variant_quantities = {}
            if len(product_data['variants']) > 1:
                if supplier is not None:
                    supplier_mapping = product.get_suppliers_mapping()
                    for variant in product_data['variants']:
                        v_id = variant['id']
                        supplier_source = supplier_mapping.get(str(v_id))
                        if supplier_source is not None:
                            supplier_id = supplier_source['supplier']
                            variant_source_id = ProductSupplier.objects.get(id=supplier_id).get_source_id()
                            inv = UserSupplement.objects.get(id=variant_source_id).pl_supplement.inventory
                            product.set_variant_quantity(quantity=inv, variant_id=v_id)
                            time.sleep(0.5)
            else:
                variant_quantities = [{
                    'variant_ids': None,
                    'sku': None,
                    'sku_short': None,
                    'availabe_qty': product.default_supplier.user_supplement.pl_supplement.inventory,
                    'ships_from_id': None,
                    'ships_from_title': None,
                }]
        else:
            variant_quantities = get_supplier_variants(product.default_supplier.supplier_type(), product.default_supplier.get_source_id())

        if product_data:
            if variant_quantities:
                for variant in variant_quantities:
                    sku = variant.get('sku')
                    if not sku:
                        if len(product_data['variants']) == 1 and len(variant_quantities) == 1:
                            idx = 0
                        else:
                            continue
                    else:
                        idx = variant_index_from_supplier_sku(product, sku, product_data['variants'])
                        if idx is None:
                            if len(product_data['variants']) == 1 and len(variant_quantities) == 1:
                                idx = 0
                            else:
                                continue

                    product.set_variant_quantity(quantity=variant['availabe_qty'], variant=product_data['variants'][idx])
                    time.sleep(0.5)
            elif product.default_supplier.supplier_type() == 'aliexpress':
                for variant in product_data['variants']:
                    product.set_variant_quantity(quantity=100, variant=variant)
                    time.sleep(0.5)

        cache.delete('product_inventory_sync_shopify_{}_{}'.format(product.id, product.default_supplier.id))

    except ShopifyProduct.DoesNotExist:
        pass
    except Exception as e:
        capture_exception()

        if not self.request.called_directly:
            countdown = retry_countdown('retry_sync_shopify_{}'.format(product_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def update_shopify_product(self, store_id, shopify_id, shopify_product=None, product_id=None):
    utils.update_shopify_product(self, store_id, shopify_id, shopify_product=shopify_product, product_id=product_id)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def sync_shopify_orders(self, store_id, elastic=False):
    try:
        start_time = arrow.now()

        store = ShopifyStore.objects.get(id=store_id)
        es = order_utils.get_elastic() if elastic else None

        max_days_sync = 30
        saved_count = order_utils.store_saved_orders(store, es=es, days=max_days_sync)
        shopify_count = store.get_orders_count(all_orders=True, days=max_days_sync)

        need_import = shopify_count - saved_count

        if need_import > 0:
            capture_message('Sync Store Orders', level='info', extra={
                'store': store.title,
                'es': bool(es),
                'missing': need_import
            }, tags={
                'store': store.title,
                'es': bool(es),
            })

            imported = 0
            params = {
                'fields': 'id',
                'created_at_min': arrow.utcnow().replace(days=-abs(max_days_sync)).isoformat()
            }

            api = ShopifyAPI(store)
            for shopify_orders in api.paginate_orders(**params):
                if imported >= need_import:
                    break

                shopify_order_ids = [o['id'] for o in shopify_orders]

                if not shopify_order_ids:
                    break

                missing_order_ids = order_utils.find_missing_order_ids(store, shopify_order_ids, es=es)

                for i in missing_order_ids:
                    update_shopify_order.apply_async(
                        args=[store_id, i],
                        kwargs={'from_webhook': False},
                        countdown=imported)

                    imported += 1

                    store.pusher_trigger('order-sync-status', {
                        'curreny': imported,
                        'total': need_import
                    })

            took = (arrow.now() - start_time).seconds
            print('Sync Need: {}, Total: {}, Imported: {}, Store: {}, Took: {}s'.format(
                need_import, shopify_count, imported, store.shop, took))

    except Exception:
        capture_exception()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def update_shopify_order(self, store_id, order_id, shopify_order=None, from_webhook=True, is_new=False):
    store = None

    try:
        store = ShopifyStore.objects.get(id=store_id)

        if not store.is_active or store.user.get_config('_disable_update_shopify_order'):
            return

        if shopify_order is None:
            shopify_order = cache.get('webhook_order_{}_{}'.format(store_id, order_id))

        if shopify_order is None:
            shopify_order = utils.get_shopify_order(store, order_id)

        with cache.lock('order_lock_{}_{}'.format(store_id, order_id), timeout=10):
            try:
                order_utils.update_shopify_order(store, shopify_order)
            except IntegrityError as e:
                raise self.retry(exc=e, countdown=30, max_retries=3)

        active_order_key = 'active_order_{}'.format(shopify_order['id'])
        if caches['orders'].get(active_order_key):
            order_note = shopify_order.get('note')
            if not order_note:
                order_note = ''

            store.pusher_trigger('order-note-update', {
                'order_id': shopify_order['id'],
                'note': order_note,
                'note_snippet': truncatewords(order_note, 10),
            })

        try:
            if is_new and not shopify_order['test']:
                ShopifyOrderRevenue.objects.create(
                    store=store,
                    user=store.user,
                    order_id=shopify_order['id'],
                    currency=shopify_order['currency'],
                    items_count=len(shopify_order['line_items']),
                    line_items_price=shopify_order['subtotal_price_set']['shop_money']['amount'],
                    shipping_price=shopify_order['total_shipping_price_set']['shop_money']['amount'],
                    total_price=shopify_order['total_price_set']['shop_money']['amount'],
                    total_price_usd=shopify_order['total_price_usd'],
                )
        except:
            capture_exception(level='warning')

    except AssertionError:
        capture_message('Store is being imported', extra={'store': store})

    except ShopifyStore.DoesNotExist:
        capture_exception()

    except Exception as e:
        if http_excption_status_code(e) in [401, 402, 403, 404]:
            return

        if http_excption_status_code(e) != 429:
            capture_exception(level='warning', extra={
                'Store': store_id,
                'Order': order_id,
                'from_webhook': from_webhook,
                'Retries': self.request.retries
            }, tags={
                'store': store.shop if store else 'N/A',
                'webhook': from_webhook,
            })

        if not self.request.called_directly:
            countdown = retry_countdown('retry_order_{}'.format(order_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def update_product_connection(self, store_id, shopify_id):
    store = ShopifyStore.objects.get(id=store_id)
    order_utils.update_line_export(store, shopify_id)


@celery_app.task(base=CaptureFailure, bind=True)
def add_ordered_note(self, store_id, order_id, note):
    try:
        store = ShopifyStore.objects.get(id=store_id)

        utils.add_shopify_order_note(store, order_id, note)

    except Exception as e:
        if not self.request.called_directly:
            countdown = retry_countdown('retry_ordered_note_{}'.format(order_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=600)
def generate_feed(self, feed_id, nocache=False, by_fb=False):
    try:
        feed = FeedStatus.objects.get(id=feed_id)

        if feed.store.user.can('product_feeds.use'):
            # Generate Facebook feed
            generate_product_feed(feed, nocache=nocache)

        if feed.store.user.can('google_product_feed.use'):
            # Generate Google feed if the user set it's settings
            if feed.get_google_settings():
                generate_product_feed(feed, nocache=nocache, revision=3)

    except:
        feed.status = 0
        feed.generation_time = -1
        feed.save()

        capture_exception()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=600)
def generate_chq_feed(self, feed_id, nocache=False, by_fb=False):
    try:
        feed = CommerceHQFeedStatus.objects.get(id=feed_id)
        generate_chq_product_feed(feed, nocache=nocache)

    except:
        feed.status = 0
        feed.generation_time = -1
        feed.save()

        capture_exception()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=600)
def generate_woo_feed(self, feed_id, nocache=False, by_fb=False):
    try:
        feed = WooFeedStatus.objects.get(id=feed_id)

        if feed.store.user.can('product_feeds.use'):
            generate_woo_product_feed(feed, nocache=nocache)

        if feed.store.user.can('google_product_feed.use'):
            # Generate Google feed if the user set it's settings
            if feed.get_google_settings():
                generate_woo_product_feed(feed, nocache=nocache, revision=3)

    except:
        feed.status = 0
        feed.generation_time = -1
        feed.save()

        capture_exception()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=600)
def generate_gear_feed(self, feed_id, nocache=False, by_fb=False):
    try:
        feed = GearBubbleFeedStatus.objects.get(id=feed_id)
        generate_gear_product_feed(feed, nocache=nocache)

    except:
        feed.status = 0
        feed.generation_time = -1
        feed.save()

        capture_exception()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=600)
def generate_gkart_feed(self, feed_id, nocache=False, by_fb=False):
    try:
        feed = GrooveKartFeedStatus.objects.get(id=feed_id)

        if feed.store.user.can('product_feeds.use'):
            # Generate Facebook feed
            generate_gkart_product_feed(feed, nocache=nocache)

        if feed.store.user.can('google_product_feed.use'):
            # Generate Google feed if the user set it's settings
            if feed.get_google_settings():
                generate_gkart_product_feed(feed, nocache=nocache, revision=3)

    except:
        feed.status = 0
        feed.generation_time = -1
        feed.save()

        capture_exception()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=600)
def generate_bigcommerce_feed(self, feed_id, nocache=False, by_fb=False):
    try:
        feed = BigCommerceFeedStatus.objects.get(id=feed_id)

        if feed.store.user.can('product_feeds.use'):
            generate_bigcommerce_product_feed(feed, nocache=nocache)

        if feed.store.user.can('google_product_feed.use'):
            # Generate Google feed if the user set it's settings
            if feed.get_google_settings():
                generate_bigcommerce_product_feed(feed, nocache=nocache, revision=3)

    except:
        feed.status = 0
        feed.generation_time = -1
        feed.save()

        capture_exception()


@celery_app.task(base=CaptureFailure, ignore_result=True)
def manage_product_change(change_id):
    try:
        product_change = ProductChange.objects.get(pk=change_id)
        manager = ProductChangeManager.initialize(product_change)
        manager.apply_changes()

    except ProductChange.DoesNotExist:
        pass

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def bulk_edit_products(self, store, products):
    """ Bulk Edit Connected products """

    store = ShopifyStore.objects.get(id=store)

    errors = []
    for product in products:
        try:
            api_url = store.api('products', product['id'])
            title = product['title']
            del product['title']

            rep = requests.put(api_url, json={'product': product})
            rep.raise_for_status()

            time.sleep(0.5)

        except:
            errors.append(truncatewords(title, 10))
            capture_exception()

    store.pusher_trigger('bulk-edit-connected', {
        'task': self.request.id,
        'errors': errors
    })


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def search_shopify_products(self, store, title, category, status, ppp, page):
    store = ShopifyStore.objects.get(id=store)

    all_products = []
    errors = []
    page = safe_int(page, 1)
    post_per_page = safe_int(ppp)
    max_products = post_per_page * (page + 1)

    try:
        products = utils.get_shopify_products(store=store, all_products=True, max_products=max_products,
                                              title=title, product_type=category, status=status,
                                              fields='id,image,title,product_type', sleep=0.5)
        for product in products:
            all_products.append(product)
    except:
        errors.append('Server Error')
        capture_exception()

    paginator = SimplePaginator(all_products, post_per_page)
    page = min(max(1, page), paginator.num_pages)
    cache.set('shopify_products_%s' % self.request.id, paginator.page(page).object_list, timeout=60)

    store.pusher_trigger('shopify-products-found', {
        'task': self.request.id,
        'errors': errors,
        'current': page,
        'prev': page > 1,
        'next': paginator.num_pages > page
    })


@celery_app.task(bind=True, base=CaptureFailure)
def generate_order_export(self, order_export_id):
    try:
        order_export = OrderExport.objects.get(pk=order_export_id)

        api = ShopifyOrderExport(order_export)
        api.generate_export()
    except:
        capture_exception()


@celery_app.task(bind=True, base=CaptureFailure)
def generate_tracked_order_export(self, params):
    try:
        track_order_export = ShopifyTrackOrderExport(params["store_id"])
        track_order_export.generate_tracked_export(params)

    except:
        capture_exception()

    if params.get('cache_key'):
        cache.delete(params['cache_key'])


@celery_app.task(bind=True, base=CaptureFailure)
def generate_order_export_query(self, order_export_id):
    try:
        order_export = OrderExport.objects.get(pk=order_export_id)

        api = ShopifyOrderExport(order_export)
        api.generate_query(send_email=False)
    except:
        capture_exception()


@celery_app.task(bind=True, base=CaptureFailure)
def create_image_zip(self, images, product_id):
    try:
        product = ShopifyProduct.objects.get(pk=product_id)
        cache_key = 'image_zip_{}_{}'.format(product_id, hash_list(images))
        url = cache.get(cache_key)
        if not url:
            filename = tempfile.mktemp(suffix='.zip', prefix='{}-'.format(product_id))

            with zipfile.ZipFile(filename, 'w') as images_zip:
                for i, img_url in enumerate(images):
                    if img_url.startswith('//'):
                        img_url = 'http:{}'.format(img_url)

                    image_name = 'image-{}.{}'.format(i + 1, get_fileext_from_url(img_url, fallback='jpg'))
                    images_zip.writestr(image_name, requests.get(img_url).content)

            product_filename = 'product-images.zip'
            if slugify(product.title):
                product_filename = f'{slugify(product.title)[:100]}-images.zip'

            s3_path = f'product-downloads/{product.id}/{product_filename}'
            url = utils.aws_s3_upload(s3_path, input_filename=filename, mimetype='application/zip')

            cache.set(cache_key, url, timeout=3600 * 24)

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


@celery_app.task(base=CaptureFailure, bind=True)
def order_save_changes(self, data):
    order_id = None
    try:
        updater = utils.ShopifyOrderUpdater()
        updater.fromJSON(data)

        order_id = updater.order_id

        updater.save_changes()

    except Exception as e:
        if http_excption_status_code(e) not in [401, 402, 403, 404, 429]:
            capture_exception(extra=http_exception_response(e))

        if not self.request.called_directly:
            countdown = retry_countdown('retry_ordered_tags_{}'.format(order_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure, bind=True)
def sync_product_exclude(self, store_id, product_id):
    try:
        from shopify_orders import tasks as order_tasks

        store = ShopifyStore.objects.get(id=store_id)

        print('PSync', store.title, product_id)

        filtered_map = store.shopifyproduct_set.filter(is_excluded=True).values_list('shopify_id', flat=True)
        es_search_enabled = order_utils.is_store_indexed(store=store)

        orders = ShopifyOrder.objects.filter(store=store, shopifyorderline__product_id=product_id) \
                                     .prefetch_related('shopifyorderline_set') \
                                     .only('id', 'connected_items', 'need_fulfillment') \
                                     .distinct()

        orders_count = orders.count()

        print('PSync Orders', orders_count)

        start = 0
        steps = 5000
        count = 0
        report = max(10, orders_count / 10)

        while start <= orders_count:
            with transaction.atomic():
                for order in orders[start:start + steps]:
                    lines = order.shopifyorderline_set.all()
                    connected_items = 0
                    need_fulfillment = len(lines)

                    for line in lines:
                        if line.product_id:
                            connected_items += 1

                        if line.track_id or line.fulfillment_status == 'fulfilled' or line.shopify_product in filtered_map:
                            need_fulfillment -= 1

                    if order.need_fulfillment != need_fulfillment or order.connected_items != connected_items:
                        ShopifyOrder.objects.filter(id=order.id).update(need_fulfillment=need_fulfillment, connected_items=connected_items)

                        if es_search_enabled:
                            order_tasks.index_shopify_order.delay(order.id)

                    count += 1

                    if count % report == 0:
                        store.pusher_trigger('product-exclude', {
                            'total': orders_count,
                            'progress': count,
                            'product': product_id,
                        })

            start += steps

        store.pusher_trigger('product-exclude', {
            'total': orders_count,
            'progress': orders_count,
            'product': product_id,
        })

    except Exception:
        capture_exception()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def calculate_sales(self, user_id, period):
    try:
        rejected_status = ALIEXPRESS_REJECTED_STATUS

        users_affiliate = {}
        sales_dropified = 0
        sales_users = 0

        if not period:
            return

        for profile in UserProfile.objects.filter(config__contains='aliexpress_affiliate_tracking').select_related('user'):
            if all(profile.get_config_value(['aliexpress_affiliate_key', 'aliexpress_affiliate_tracking'])):
                users_affiliate[profile.user.id] = 'UserAliexpress'

        for profile in UserProfile.objects.filter(config__contains='admitad_site_id').select_related('user'):
            if profile.get_config_value('admitad_site_id'):
                users_affiliate[profile.user.id] = 'UserAdmitad'

        order_tracks = ShopifyOrderTrack.objects.exclude(data='')
        if period:
            period = timezone.now() - timedelta(days=int(period))
            first_track = order_tracks.filter(created_at__gte=period).order_by('id')[0:1].first()
            order_tracks = order_tracks.filter(id__gte=first_track.id)

        steps = 10000
        start = 0
        ignored_tracks = 0

        seen_source_ids = []
        added_tracks = 1
        while added_tracks:
            added_tracks = 0

            for order_track in order_tracks[start:start + steps].values('user_id', 'source_id', 'data'):
                added_tracks += 1

                try:
                    source_id = int(order_track['source_id'])
                except:
                    source_id = None

                if not source_id or source_id in seen_source_ids or 'order_details' not in order_track['data']:
                    ignored_tracks += 1
                    continue

                sale = 0
                try:
                    data = json.loads(order_track['data'])
                    sale = float(data['aliexpress']['order_details']['cost']['products'])
                    if data['aliexpress']['end_reason'] and data['aliexpress']['end_reason'].lower() in rejected_status:
                        sale = 0

                except:
                    sale = 0

                if not sale:
                    ignored_tracks += 1
                    continue

                affiliate = users_affiliate.get(order_track['user_id'])
                if not affiliate:
                    affiliate = 'ShopifiedApp'

                if affiliate == 'ShopifiedApp':
                    sales_dropified += sale
                if affiliate == 'UserAdmitad':
                    sales_users += sale

                seen_source_ids.append(source_id)

            start += steps

        data = {
            'task': self.request.id,
            'sales_dropified': '{:,.2f}'.format(sales_dropified),
            'sales_users': '{:,.2f}'.format(sales_users),
            'sales_dropified_commission': '{:,.2f}'.format(sales_dropified * 0.12),
            'sales_users_commission': '{:,.2f}'.format(sales_users * 0.04),
        }

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger("user_{}".format(user_id), 'sales-calculated', data)

    except:
        capture_exception()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def calculate_user_statistics(self, user_id):
    try:
        user = User.objects.get(id=user_id)

        if user.get_config('_disbale_user_statistics'):
            return

        total_products_count = 0
        stores = user.profile.get_shopify_stores()

        stores_data = []
        for store in stores:
            info = {
                'id': store.id,
                'products_connected': store.connected_count(),
                'products_saved': store.saved_count(),
            }

            stores_data.append(info)

            total_products_count += info['products_connected'] + info['products_saved']

        cache.set('user_statistics_{}'.format(user_id), stores_data, timeout=3600)

        if total_products_count > 10000 and user.get_config('_disbale_user_statistics') is not False:
            user.set_config('_disbale_user_statistics', True)

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger("user_{}".format(user_id), 'user-statistics-calculated', {'task': self.request.id})

    except:
        capture_exception()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def shopify_orders_risk(self, store, order_ids):
    store = ShopifyStore.objects.get(id=store)
    order_risks = dict(ShopifyOrderRisk.objects.filter(store=store, order_id__in=order_ids).values_list('order_id', 'data'))

    errors = []
    orders = {}
    for order_id in order_ids:
        if int(order_id) in order_risks:
            risks = json.loads(order_risks[int(order_id)])
        else:
            try:
                api_url = store.api('orders', order_id, 'risks')
                rep = requests.get(api_url)
                rep.raise_for_status()

                risks = rep.json()['risks']

                ShopifyOrderRisk.objects.create(
                    store=store,
                    order_id=order_id,
                    data=json.dumps([{
                        'score': i['score'],
                        'message': i['message']
                    } for i in risks if i.get('display', True)])
                )

                if int(rep.headers['X-Shopify-Shop-Api-Call-Limit'].split('/')[0]) > 20:
                    time.sleep(0.5)

            except:
                risks = []
                errors.append(order_id)
                capture_exception()

        score = 0.0

        for s in risks:
            if score < float(s['score']):
                score = float(s['score'])

            if 'shopify recommendation' in s.get('message', '').lower():
                score = float(s['score'])
                break

        orders[str(order_id)] = score

    store.pusher_trigger('order-risks', {
        'task': self.request.id,
        'orders': orders,
        'errors': errors
    })


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def products_supplier_sync(self, store_id, products, sync_price, price_markup, compare_markup, sync_inventory, cache_key):
    store = ShopifyStore.objects.get(id=store_id)

    products = ShopifyProduct.objects.filter(id__in=products, user=store.user, store=store, shopify_id__gt=0)
    total_count = 0
    for product in products:
        if product.have_supplier() and (product.default_supplier.is_aliexpress or product.default_supplier.is_ebay):
            total_count += 1

    push_data = {
        'task': self.request.id,
        'count': total_count,
        'success': 0,
        'fail': 0,
    }
    store.pusher_trigger('products-supplier-sync', push_data)

    for product in products:
        if not product.have_supplier() or not (product.default_supplier.is_aliexpress or product.default_supplier.is_ebay):
            continue

        supplier = product.default_supplier
        push_data['id'] = product.id
        push_data['title'] = product.title
        push_data['shopify_link'] = product.shopify_link()
        push_data['supplier_link'] = supplier.product_url
        push_data['status'] = 'ok'
        push_data['error'] = None

        try:
            # Fetch supplier variants
            supplier_variants = get_supplier_variants(supplier.supplier_type(), supplier.get_source_id())

            supplier_prices = [v['price'] for v in supplier_variants]
            supplier_min_price = min(supplier_prices)
            supplier_max_price = max(supplier_prices)
        except Exception:
            push_data['status'] = 'fail'
            push_data['error'] = 'Failed to load supplier data'
            push_data['fail'] += 1
            store.pusher_trigger('products-supplier-sync', push_data)
            continue

        try:
            # Fetch shopify variants
            product_data = utils.get_shopify_product(store, product.shopify_id)
        except Exception:
            push_data['status'] = 'fail'
            push_data['error'] = 'Failed to load shopify data'
            push_data['fail'] += 1
            store.pusher_trigger('products-supplier-sync', push_data)
            continue

        try:
            # Check if there's only one price
            seem_price = (len('variants') == 1
                          or len(set([v['price'] for v in product_data['variants']])) == 1
                          or len(supplier_variants) == 1
                          or supplier_min_price == supplier_max_price)

            # New Data
            api_variants_data = [{'id': v['id']} for v in product_data['variants']]
            updated = False
            mapped_variants = {}
            unmapped_variants = []

            if sync_price and seem_price:
                # Use one price for all variants
                for i, variant in enumerate(product_data['variants']):
                    api_variants_data[i]['price'] = round(supplier_max_price * (100 + price_markup) / 100.0, 2)
                    api_variants_data[i]['compare_at_price'] = round(api_variants_data[i]['price'] * (100 + compare_markup) / 100.0, 2)
                    updated = True

            if (sync_price and not seem_price) or sync_inventory:
                for index, variant in enumerate(supplier_variants):
                    sku = variant.get('sku')
                    if not sku:
                        if len(product_data['variants']) == 1 and len(supplier_variants) == 1:
                            idx = 0
                        else:
                            continue
                    else:
                        idx = variant_index_from_supplier_sku(product, sku, product_data['variants'])
                        if idx is None:
                            if len(product_data['variants']) == 1 and len(supplier_variants) == 1:
                                idx = 0
                            else:
                                continue

                    mapped_variants[str(product_data['variants'][idx]['id'])] = True
                    # Sync price
                    if sync_price and not seem_price:
                        api_variants_data[idx]['price'] = round(supplier_variants[index]['price'] * (100 + price_markup) / 100.0, 2)
                        api_variants_data[idx]['compare_at_price'] = round(api_variants_data[idx]['price'] * (100 + compare_markup) / 100.0, 2)
                        updated = True
                    # Sync inventory
                    if sync_inventory:
                        product.set_variant_quantity(quantity=variant['availabe_qty'], variant=product_data['variants'][idx])
                        time.sleep(0.5)

                # check unmapped variants
                for variant in product_data['variants']:
                    if not mapped_variants.get(str(variant['id']), False):
                        unmapped_variants.append(variant['title'])

            if updated:
                update_endpoint = product.store.api('products', product.shopify_id)
                rep = requests.put(update_endpoint, json={
                    "product": {
                        "id": product_data['id'],
                        "variants": api_variants_data,
                    }
                })
                rep.raise_for_status()
            if len(unmapped_variants) > 0:
                push_data['error'] = 'Warning - Unmapped: {}'.format(','.join(unmapped_variants))
            push_data['success'] += 1
        except Exception:
            push_data['status'] = 'fail'
            push_data['error'] = 'Failed to update data'
            push_data['fail'] += 1

        store.pusher_trigger('products-supplier-sync', push_data)

    cache.delete(cache_key)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def product_randomize_image_names(self, product_id):
    data = {
        'task': self.request.id,
        'product': product_id,
        'total': 0,
        'success': 0,
        'fail': 0,
        'error': '',
    }

    product = ShopifyProduct.objects.get(id=product_id)
    store = product.store
    shopify_id = product.shopify_id

    images = []
    try:
        # Get shopify product images
        rep = requests.get(url=store.api('products', shopify_id, 'images'))
        rep.raise_for_status()

        images = rep.json()['images']
        data['total'] = len(images)
    except:
        data['error'] = 'Shopify API Error'

    if data['total'] == 0:
        store.pusher_trigger('product-randomize-image-names', data)
        return

    for image in images:
        try:
            data['image'] = None
            data['variants_images'] = None
            image_id = image.pop('id')

            # Post a shopify product image with new filename
            path, ext = os.path.splitext(image['src'])
            image['filename'] = '{}{}'.format(random_hash(), ext)
            rep = requests.post(
                store.api('products', shopify_id, 'images'),
                json={'image': image}
            )
            rep.raise_for_status()

            # Push image data with old image id
            new_image = rep.json()
            data['image'] = new_image
            data['image']['old_id'] = image_id
            update_product_data_images(product, image['src'], new_image['image']['src'])
            data['variants_images'] = product.parsed.get('variants_images') or {}

            # Delete a original shopify product image
            rep = requests.delete(
                store.api('products', shopify_id, 'images', image_id),
            )
            rep.raise_for_status()
            data['success'] += 1
        except:
            data['fail'] += 1
            data['error'] = 'Shopify API Error'

        store.pusher_trigger('product-randomize-image-names', data)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def store_transfer(self, options):
    try:
        from_user = User.objects.get(id=options['from']) if safe_int(options['from']) else User.objects.get(email__iexact=options['from'])
        to_user = User.objects.get(id=options['to']) if safe_int(options['to']) else User.objects.get(email__iexact=options['to'])

        store = ShopifyStore.objects.get(id=options['store'], user=from_user, is_active=True)

        for old_store in ShopifyStore.objects.filter(shop=store.shop, user=to_user, is_active=True):
            utils.detach_webhooks(old_store, delete_too=True)

            old_store.is_active = False
            old_store.save()

        store.user = to_user
        store.save()

        ShopifyProduct.objects.filter(store=store, user=from_user).update(user=to_user)
        ShopifyOrderTrack.objects.filter(store=store, user=from_user).update(user=to_user)
        ShopifyOrder.objects.filter(store=store, user=from_user).update(user=to_user)  # TODO: Elastic update
        ShopifyBoard.objects.filter(user=from_user).update(user=to_user)

        requests.post(
            url=options['response_url'],
            json={'text': ':heavy_check_mark: Store {} has been transferred to {} account'.format(store.shop, to_user.email)}
        )
    except:
        capture_exception()
        requests.post(
            url=options['response_url'],
            json={'text': ':x: Server Error when transferring {} to {} account'.format(options['shop'], options['to'])}
        )


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def store_transfer_woo(self, options):
    try:
        from_user = User.objects.get(id=options['from']) if safe_int(options['from']) else User.objects.get(email__iexact=options['from'])
        to_user = User.objects.get(id=options['to']) if safe_int(options['to']) else User.objects.get(email__iexact=options['to'])

        store = WooStore.objects.get(id=options['store'], user=from_user, is_active=True)

        for old_store in WooStore.objects.filter(user=to_user, is_active=True):
            if get_domain(old_store.api_url, full=True) == get_domain(store.api_url, full=True):
                old_store.is_active = False
                old_store.save()

        store.user = to_user
        store.save()

        WooProduct.objects.filter(store=store, user=from_user).update(user=to_user)
        WooOrderTrack.objects.filter(store=store, user=from_user).update(user=to_user)
        WooBoard.objects.filter(user=from_user).update(user=to_user)

        requests.post(
            url=options['response_url'],
            json={'text': f':heavy_check_mark: WooCommerce Store {store.api_url} has been transferred to {to_user.email} account'}
        )
    except:
        capture_exception()
        requests.post(
            url=options['response_url'],
            json={'text': f':x: Server Error when transferring {options["shop"]} to {options["to"]} account'}
        )


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def delete_shopify_store(self, store_id):
    try:
        store = ShopifyStore.objects.get(id=store_id)

        match = {
            'store': store
        }

        orders = order_utils.delete_store_orders(store)
        products = delete_model_from_db(ShopifyProduct, match)
        tracks = delete_model_from_db(ShopifyOrderTrack, match)

        capture_message('Delete Store', level='info', extra={
            'store': store.shop,
            'orders': orders,
            'products': products,
            'tracks': tracks,
        })

        requests.delete(store.api('api_permissions/current'))

        if store.user.profile.from_shopify_app_store():
            delete_user.delay(store.user.id)

        store.delete()
    except:
        capture_exception()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def delete_user(self, user_id):
    try:
        user = User.objects.get(id=user_id)

        if not user.is_subuser:
            for store in user.profile.get_shopify_stores():
                delete_shopify_store(store.id)

        products = delete_model_from_db(ShopifyProduct, {'user': user})

        user.delete()

        capture_message('Delete User', level='info', extra={'Saved Products': products})
    except:
        capture_exception()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def fulfullment_service_check(self, user_id):
    user = User.objects.get(id=user_id)

    for store in user.profile.get_shopify_stores():
        try:
            store.get_dropified_location()
        except:
            capture_exception()
