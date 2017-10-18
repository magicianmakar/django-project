from __future__ import absolute_import

import requests
import time
import tempfile
import zipfile
import os.path
import keen

from simplejson import JSONDecodeError
from datetime import timedelta

from django.db import transaction
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.cache import cache, caches
from django.template.defaultfilters import truncatewords
from django.utils import timezone
from django.utils.text import slugify

from raven.contrib.django.raven_compat.models import client as raven_client

from app.celery import celery_app, CaptureFailure, retry_countdown
from shopified_core import permissions
from shopified_core.utils import app_link

from unidecode import unidecode

from leadgalaxy.models import *
from leadgalaxy import utils
from leadgalaxy.statuspage import record_import_metric

from shopify_orders import utils as order_utils
from product_alerts.events import ProductChangeEvent

from product_feed.feed import generate_product_feed, generate_chq_product_feed, generate_woo_product_feed
from product_feed.models import FeedStatus, CommerceHQFeedStatus, WooFeedStatus

from order_exports.models import OrderExport
from order_exports.api import ShopifyOrderExportAPI

from shopify_orders.models import ShopifyOrder


@celery_app.task(base=CaptureFailure)
def export_product(req_data, target, user_id):
    start = time.time()

    store = req_data.get('store')
    data = req_data['data']
    parsed_data = json.loads(req_data['data'])
    original_data = req_data.get('original', '')
    variants_mapping = None

    user = User.objects.get(id=user_id)

    raven_client.user_context({
        'id': user.id,
        'username': user.username,
        'email': user.email
    })

    raven_client.extra_context({
        'target': target,
        'store': store,
        'product': req_data.get('product'),
        'from_extension': ('access_token' in req_data)
    })

    if store or target != 'save-for-later':
        try:
            store = ShopifyStore.objects.get(id=store)
            permissions.user_can_view(user, store)

        except (ShopifyStore.DoesNotExist, ValueError):
            raven_client.captureException()

            return {
                'error': 'Selected store (%s) not found' % (store)
            }
        except PermissionDenied as e:
            return {
                'error': "Store: {}".format(e.message)
            }

    original_url = parsed_data.get('original_url')
    if not original_url:
        original_url = req_data.get('original_url')

    if not original_url:  # Could be sent from the web app
        try:
            product = ShopifyProduct.objects.get(id=req_data.get('product'))
            permissions.user_can_edit(user, product)

            original_url = product.get_original_info().get('url', '')

        except ShopifyProduct.DoesNotExist:
            original_url = ''

        except PermissionDenied as e:
            return {
                'error': "Product: {}".format(e.message)
            }
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

    if target == 'shopify' or target == 'shopify-update':
        try:
            if target == 'shopify-update':
                product = ShopifyProduct.objects.get(id=req_data['product'])
                permissions.user_can_edit(user, product)

                api_data = parsed_data
                api_data['product']['id'] = product.get_shopify_id()

                update_endpoint = store.get_link('/admin/products/{}.json'.format(product.get_shopify_id()), api=True)
                r = requests.put(update_endpoint, json=api_data)

                del api_data
            else:
                endpoint = store.get_link('/admin/products.json', api=True)
                api_data = parsed_data

                if api_data['product'].get('variants') and len(api_data['product']['variants']) > 100:
                    api_data['product']['variants'] = api_data['product']['variants'][:100]

                r = requests.post(endpoint, json=api_data)

                if 'product' in r.json():
                    product_to_map = r.json()['product']

                    try:
                        if not product_to_map.get('images') and api_data['product'].get('images'):
                            images_fix_data = {
                                'product': {
                                    'id': product_to_map['id'],
                                    'images': api_data['product']['images']
                                }
                            }

                            try:
                                requests.put(
                                    url=store.get_link('/admin/products/{}.json'.format(product_to_map['id']), api=True),
                                    json=images_fix_data
                                ).raise_for_status()
                            except:
                                raven_client.captureException(level='warning')

                        # Variant mapping
                        variants_mapping = utils.get_mapping_from_product(product_to_map)
                        variants_mapping = json.dumps(variants_mapping)

                        # Link images with variants
                        mapped = utils.shopify_link_images(store, product_to_map)
                        if mapped:
                            r = mapped
                    except Exception as e:
                        raven_client.captureException()

                del api_data

            if 'product' not in r.json():
                rep = r.json()

                shopify_error = utils.format_shopify_error(rep)

                if 'Invalid API key or access token' in shopify_error:
                    print u'SHOPIFY EXPORT: {} - Store: {} - Link: {}'.format(
                        shopify_error, store, store.get_link('/admin/products.json', api=True)
                    ).encode('utf-8')
                else:
                    print u'SHOPIFY EXPORT: {} - Store: {} - Product: {}'.format(
                        shopify_error, store, req_data.get('product')).encode('utf-8')

                if 'requires write_products scope' in shopify_error:
                    return {'error': (u'Shopify Error: {}\n\n'
                                      'Please follow this instructions to resolve this issue:\n{}'
                                      ).format(shopify_error, app_link('pages/view/15'))}
                elif 'handle: has already been taken' in shopify_error:
                    return {'error': (u'Shopify Error: {}\n\n'
                                      'Please Change your product title by adding or removing one or more words'
                                      ).format(shopify_error)}
                elif 'Exceeded maximum number of variants allowed' in shopify_error:
                    return {'error': (u'Shopify Error: {}\n\n'
                                      'Please reduce the number of variants to 100 or less by '
                                      'removing some variant choices to meet Shopify\'s requirements.'
                                      ).format(shopify_error)}
                else:
                    return {'error': u'Shopify Error: {}'.format(shopify_error)}

        except (JSONDecodeError, requests.exceptions.ConnectTimeout):
            raven_client.captureException(extra={
                'rep': r.text
            })

            return {'error': 'Shopify API is not available, please try again.'}

        except ShopifyProduct.DoesNotExist:
            raven_client.captureException()
            return {
                'error': "Product {} does not exist".format(req_data.get('product'))
            }

        except PermissionDenied as e:
            raven_client.captureException()
            return {
                'error': "Product: {}".format(e.message)
            }

        except:
            raven_client.captureException()
            print 'WARNING: SHOPIFY EXPORT EXCEPTION:'

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
                            product_url=original_url,
                            supplier_name=supplier.get('name'),
                            supplier_url=supplier.get('url'),
                            variants_map=variants_mapping,
                            is_default=True
                        )
                    else:
                        product.default_supplier.variants_map = variants_mapping
                        product.default_supplier.save()

                    product.save()

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
            else:
                product = None
        else:
            # messages.success(request, 'Product updated in Shopify.')
            pass

        # update product collections
        collections = parsed_data.get('collections')
        if collections is not None:
            utils.ProductCollections().link_product_collection(product, collections)

        product.update_data(data)

    elif target == 'save-for-later':  # save for later
        if 'product' in req_data:
            # Saved product update
            try:
                product = ShopifyProduct.objects.get(id=req_data['product'])
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

            boards = parsed_data.get('boards', [])
            if boards:
                utils.attach_boards_with_product(user, product, boards)

        else:  # New product to save

            can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)
            if not can_add:
                return {
                    'error': 'Your current plan allow up to %d saved products, currently you have %d saved products.'
                             % (total_allowed, user_count)
                }

            is_active = req_data.get('activate', True)

            try:
                product = ShopifyProduct(store=store, user=user.models_user, notes=req_data.get('notes', ''), is_active=is_active)
                product.update_data(data)
                product.set_original_data(original_data, commit=False)

                permissions.user_can_add(user, product)

                product.save()

                boards = parsed_data.get('boards', [])
                if boards:
                    utils.attach_boards_with_product(user, product, boards)

                supplier_info = product.get_supplier_info()
                supplier = ProductSupplier.objects.create(
                    store=store,
                    product=product,
                    product_url=original_url,
                    supplier_name=supplier_info.get('name'),
                    supplier_url=supplier_info.get('url'),
                    is_default=True
                )

                product.set_default_supplier(supplier, commit=True)

            except PermissionDenied as e:
                raven_client.captureException()
                return {
                    'error': "Add Product: {}".format(e.message)
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
            raven_client.captureException(level='warning')

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


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def update_shopify_product(self, store_id, shopify_id, shopify_product=None, product_id=None):
    try:
        store = ShopifyStore.objects.get(id=store_id)
        try:
            if product_id:
                product = ShopifyProduct.objects.get(store=store, id=product_id)
            else:
                product = ShopifyProduct.objects.get(store=store, shopify_id=shopify_id)
        except:
            return

        if shopify_product is None:
            shopify_product = cache.get('webhook_product_{}_{}'.format(store_id, shopify_id))

        if shopify_product is None:
            rep = requests.get(url=store.get_link('/admin/products/{}.json'.format(shopify_id), api=True))

            if rep.ok:
                shopify_product = rep.json()['product']
            else:
                if rep.status_code in [401, 402, 403, 404]:
                    return
                else:
                    rep.raise_for_status()

        product_data = json.loads(product.data)
        product_data['title'] = shopify_product['title']
        product_data['type'] = shopify_product['product_type']
        product_data['tags'] = shopify_product['tags']
        product_data['images'] = [i['src'] for i in shopify_product['images']]
        product_data['description'] = shopify_product['body_html']
        product_data['published'] = shopify_product.get('published_at') is not None

        prices = [utils.safeFloat(i['price'], 0.0) for i in shopify_product['variants']]
        compare_at_prices = [utils.safeFloat(i['compare_at_price'], 0.0) for i in shopify_product['variants']]

        if len(set(prices)) == 1:  # If all variants have the same price
            product_data['price'] = prices[0]
            product_data['price_range'] = None
        else:
            product_data['price'] = min(prices)
            product_data['price_range'] = [min(prices), max(prices)]

        if len(set(compare_at_prices)) == 1:  # If all variants have the same compare at price
            product_data['compare_at_price'] = compare_at_prices[0]
        else:
            product_data['compare_at_price'] = max(compare_at_prices)

        product.data = json.dumps(product_data)
        product.save()

        # Delete Product images cache
        ShopifyProductImage.objects.filter(store=store, product=shopify_product['id']).delete()

        # update collections
        utils.ProductCollections().update_product_collects_shopify_id(product)

    except ShopifyStore.DoesNotExist:
        raven_client.captureException()

    except Exception as e:
        raven_client.captureException(level='warning', extra={
            'Store': store.title,
            'Product': shopify_id,
            'Retries': self.request.retries
        })

        if not self.request.called_directly:
            countdown = retry_countdown('retry_product_{}'.format(shopify_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def sync_shopify_orders(self, store_id):
    try:
        start_time = arrow.now()

        store = ShopifyStore.objects.get(id=store_id)
        orders = ShopifyOrder.objects.filter(store=store)
        shopify_count = store.get_orders_count(all_orders=True)
        db_count = orders.count()
        need_import = shopify_count - db_count

        if shopify_count > db_count:
            imported = 0
            page = 1
            countdown = 0

            while imported < need_import:
                shopify_orders = utils.get_shopify_orders(store, page=page, limit=250, fields='id')
                shopify_order_ids = [o['id'] for o in shopify_orders]

                order_ids = list(ShopifyOrder.objects.filter(store=store, order_id__in=shopify_order_ids)
                                                     .values_list('order_id', flat=True))

                for shopify_order_id in shopify_order_ids:
                    if shopify_order_id not in order_ids:
                        update_shopify_order.apply_async(
                            args=[store_id, shopify_order_id],
                            countdown=countdown)

                        imported += 1
                        countdown += 1

                        store.pusher_trigger('order-sync-status', {
                            'curreny': imported,
                            'total': need_import
                        })

                page += 1

        print 'Sync {}/{} Orders @{} Complete in {}s'.format(need_import, shopify_count, store.id, (arrow.now() - start_time).seconds)

    except Exception:
        raven_client.captureException()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def update_shopify_order(self, store_id, order_id, shopify_order=None, from_webhook=True):
    try:
        store = ShopifyStore.objects.get(id=store_id)

        if shopify_order is None:
            shopify_order = cache.get('webhook_order_{}_{}'.format(store_id, order_id))

        if shopify_order is None:
            shopify_order = utils.get_shopify_order(store, order_id)

        for line in shopify_order['line_items']:
            fulfillment_status = line.get('fulfillment_status')
            manual_fulfillement = line.get('fulfillment_service') == 'manual'

            if not fulfillment_status:
                fulfillment_status = ''

            if manual_fulfillement:
                ShopifyOrderTrack.objects.filter(store=store, order_id=shopify_order['id'], line_id=line['id']) \
                                         .update(shopify_status=fulfillment_status)

        with cache.lock('order_lock_{}_{}'.format(store_id, order_id), timeout=10):
            order_utils.update_shopify_order(store, shopify_order)

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

    except AssertionError:
        raven_client.captureMessage('Store is being imported', extra={'store': store})

    except ShopifyStore.DoesNotExist:
        raven_client.captureException()

    except Exception as e:
        raven_client.captureException(level='warning', extra={
            'Store': store_id,
            'Order': order_id,
            'from_webhook': from_webhook,
            'Retries': self.request.retries
        })

        if not self.request.called_directly:
            countdown = retry_countdown('retry_order_{}'.format(order_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def update_product_connection(self, store_id, shopify_id):
    store = ShopifyStore.objects.get(id=store_id)
    order_utils.update_line_export(store, shopify_id)


@celery_app.task(base=CaptureFailure, ignore_result=True)
def smartmemeber_webhook_call(subdomain, data):
    try:
        data['cprodtitle'] = 'Shopified App Success Club OTO3'
        data['cproditem'] = '205288'

        rep = requests.post(
            url='https://api.smartmember.com/transaction?type=jvzoo&subdomain={}'.format(subdomain),
            data=data
        )

        raw_rep = rep.text  # variable will be accessible in Sentry
        assert len(raw_rep) and 'email' in rep.json()

    except:
        raven_client.captureException()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def mark_as_ordered_note(self, store_id, order_id, line_id, source_id):
    try:
        store = ShopifyStore.objects.get(id=store_id)
        order_line, current_note = utils.get_shopify_order_line(store, order_id, line_id, note=True)
        if order_line:
            note = u'Aliexpress Order ID: {0}\n' \
                   'http://trade.aliexpress.com/order_detail.htm?orderId={0}\n' \
                   'Shopify Product: {1} / {2}'.format(source_id, order_line.get('name'),
                                                       order_line.get('variant_title'))
        else:
            note = 'Aliexpress Order ID: {0}\n' \
                   'http://trade.aliexpress.com/order_detail.htm?orderId={0}\n'.format(source_id)

        utils.add_shopify_order_note(store, order_id, note, current_note=current_note)

    except Exception as e:
        if not self.request.called_directly:
            countdown = retry_countdown('retry_mark_ordered_{}'.format(order_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure, bind=True)
def add_ordered_note(self, store_id, order_id, note):
    try:
        store = ShopifyStore.objects.get(id=store_id)

        utils.add_shopify_order_note(store, order_id, note)

    except Exception as e:
        if not self.request.called_directly:
            countdown = retry_countdown('retry_ordered_note_{}'.format(order_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure, ignore_result=True)
def invite_user_to_slack(slack_teams, data):
    for team in slack_teams.split(','):
        utils.slack_invite(data, team=team)


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=600)
def generate_feed(self, feed_id, nocache=False, by_fb=False):
    try:
        feed = FeedStatus.objects.get(id=feed_id)
        generate_product_feed(feed, nocache=nocache)

    except:
        feed.status = 0
        feed.generation_time = -1
        feed.save()

        raven_client.captureException()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=600)
def generate_chq_feed(self, feed_id, nocache=False, by_fb=False):
    try:
        feed = CommerceHQFeedStatus.objects.get(id=feed_id)
        generate_chq_product_feed(feed, nocache=nocache)

    except:
        feed.status = 0
        feed.generation_time = -1
        feed.save()

        raven_client.captureException()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=600)
def generate_woo_feed(self, feed_id, nocache=False, by_fb=False):
    try:
        feed = WooFeedStatus.objects.get(id=feed_id)
        generate_woo_product_feed(feed, nocache=nocache)

    except:
        feed.status = 0
        feed.generation_time = -1
        feed.save()

        raven_client.captureException()


@celery_app.task(base=CaptureFailure, ignore_result=True)
def product_change_alert(change_id):
    try:
        product_change = AliexpressProductChange.objects.get(pk=change_id)
        product_change_event = ProductChangeEvent(product_change)
        product_change_event.take_action()

    except:
        raven_client.captureException()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def bulk_edit_products(self, store, products):
    """ Bulk Edit Connected products """

    store = ShopifyStore.objects.get(id=store)

    errors = []
    for product in products:
        try:
            api_url = store.get_link('/admin/products/{}.json'.format(product['id']), api=True)
            title = product['title']
            del product['title']

            rep = requests.put(api_url, json={'product': product})
            rep.raise_for_status()

            time.sleep(0.5)

        except:
            errors.append(truncatewords(title, 10))
            raven_client.captureException()

    store.pusher_trigger('bulk-edit-connected', {
        'task': self.request.id,
        'errors': errors
    })


@celery_app.task(bind=True, base=CaptureFailure)
def generate_order_export(self, order_export_id):
    try:
        order_export = OrderExport.objects.get(pk=order_export_id)

        api = ShopifyOrderExportAPI(order_export)
        api.generate_export()
    except Exception as exc:
        raven_client.captureException()

        raise self.retry(exc=exc, countdown=5, max_retries=3)


@celery_app.task(bind=True, base=CaptureFailure)
def generate_order_export_query(self, order_export_id):
    try:
        order_export = OrderExport.objects.get(pk=order_export_id)

        api = ShopifyOrderExportAPI(order_export)
        api.generate_query(send_email=False)
    except Exception as exc:
        raven_client.captureException()

        raise self.retry(exc=exc, countdown=5, max_retries=3)


@celery_app.task(bind=True, base=CaptureFailure)
def create_image_zip(self, images, product_id):
    try:
        product = ShopifyProduct.objects.get(pk=product_id)
        cache_key = 'image_zip_{}_{}'.format(product_id, utils.hash_list(images))
        url = cache.get(cache_key)
        if not url:
            filename = tempfile.mktemp(suffix='.zip', prefix='{}-'.format(product_id))

            with zipfile.ZipFile(filename, 'w') as images_zip:
                for i, img_url in enumerate(images):
                    if img_url.startswith('//'):
                        img_url = u'http:{}'.format(img_url)

                    image_name = u'image-{}.{}'.format(i + 1, utils.get_fileext_from_url(img_url, fallback='jpg'))
                    images_zip.writestr(image_name, requests.get(img_url).content)

            s3_path = os.path.join('product-downloads', str(product.id), u'{}.zip'.format(slugify(unidecode(product.title))))
            url = utils.aws_s3_upload(s3_path, input_filename=filename)

            cache.set(cache_key, url, timeout=3600 * 24)

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


@celery_app.task(base=CaptureFailure, bind=True)
def order_save_changes(self, data):
    order_id = None
    try:
        updater = utils.ShopifyOrderUpdater()
        updater.fromJSON(data)

        order_id = updater.order_id

        updater.save_changes()

    except Exception as e:
        response = ''
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            response = e.response.text

        raven_client.captureException(
            extra={'response': response}
        )

        if not self.request.called_directly:
            countdown = retry_countdown('retry_ordered_tags_{}'.format(order_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@celery_app.task(base=CaptureFailure, bind=True)
def sync_product_exclude(self, store_id, product_id):
    try:
        store = ShopifyStore.objects.get(id=store_id)

        print 'PSync', store.title, product_id

        filtered_map = store.shopifyproduct_set.filter(is_excluded=True).values_list('shopify_id', flat=True)

        orders = ShopifyOrder.objects.filter(store=store, shopifyorderline__product_id=product_id) \
                                     .prefetch_related('shopifyorderline_set') \
                                     .only('id', 'connected_items', 'need_fulfillment') \
                                     .distinct()

        orders_count = orders.count()

        print 'PSync Orders', orders_count

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
        raven_client.captureException()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def calculate_sales(self, user_id, period):
    try:
        rejected_status = [
            'buyer_pay_timeout', 'risk_reject_closed', 'buyer_accept_goods_timeout',
            'buyer_cancel_notpay_order', 'cancel_order_close_trade', 'seller_send_goods_timeout',
            'buyer_cancel_order_in_risk', 'buyer_accept_goods', 'seller_accept_issue_no_goods_return',
            'seller_response_issue_timeout']

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
            # order_tracks = order_tracks.filter(created_at__gte=period).order_by('id')
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
        raven_client.captureException()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def calculate_user_statistics(self, user_id):
    try:
        user = User.objects.get(id=user_id)
        stores = user.profile.get_shopify_stores()

        stores_data = []
        for store in stores:
            stores_data.append({
                'id': store.id,
                'products_connected': store.connected_count(),
                'products_saved': store.saved_count(),
            })

        cache.set('user_statistics_{}'.format(user_id), stores_data, timeout=3600)

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger("user_{}".format(user_id), 'user-statistics-calculated', {'task': self.request.id})

    except:
        raven_client.captureException()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=30)
def keen_add_event(self, event_name, event_data):
    try:
        keen.add_event(event_name, event_data)
    except:
        raven_client.captureException(level='warning')
