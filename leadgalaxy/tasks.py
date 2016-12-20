import os
import requests
import time
import random
from celery import Celery
from celery import Task
from simplejson import JSONDecodeError

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.cache import cache
from django.template.defaultfilters import truncatewords
from raven.contrib.django.raven_compat.models import client as raven_client
from raven.contrib.celery import register_signal

from leadgalaxy.models import *
from leadgalaxy import utils
from leadgalaxy.statuspage import record_import_metric

from shopify_orders import utils as order_utils
from product_alerts import events as product_alerts_events

from product_feed.feed import generate_product_feed
from product_feed.models import FeedStatus

app = Celery('shopified')

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object('django.conf:settings')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# hook into the Celery error handler
if hasattr(settings, 'RAVEN_CONFIG'):
    register_signal(raven_client)


class CaptureFailure(Task):
    abstract = True

    def after_return(self, *args, **kwargs):
        raven_client.context.clear()


def retry_countdown(key, retries):
    retries = max(1, retries)
    countdown = cache.get(key, random.randint(10, 30)) + random.randint(retries, retries * 60) + (60 * retries)
    cache.set(key, countdown + random.randint(5, 30), timeout=countdown + 60)

    return countdown


@app.task(base=CaptureFailure)
def export_product(req_data, target, user_id):
    start = time.time()

    store = req_data.get('store')
    data = req_data['data']
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
            user.can_view(store)

        except (ShopifyStore.DoesNotExist, ValueError):
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

    if not original_url:  # Could be sent from the web app
        try:
            product = ShopifyProduct.objects.get(id=req_data.get('product'))
            user.can_edit(product)

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
                user.can_edit(product)

                api_data = json.loads(data)
                api_data['product']['id'] = product.get_shopify_id()

                update_endpoint = store.get_link('/admin/products/{}.json'.format(product.get_shopify_id()), api=True)
                r = requests.put(update_endpoint, json=api_data)
            else:
                endpoint = store.get_link('/admin/products.json', api=True)
                r = requests.post(endpoint, json=json.loads(data))

                if 'product' in r.json():
                    product_to_map = r.json()['product']

                    try:
                        # Variant mapping
                        variants_mapping = utils.get_mapping_from_product(product_to_map)
                        variants_mapping = json.dumps(variants_mapping)

                        # Link images with variants
                        mapped = utils.shopify_link_images(store, product_to_map)
                        if mapped:
                            r = mapped
                    except Exception as e:
                        raven_client.captureException()

            if 'product' not in r.json():
                rep = r.json()

                shopify_error = utils.format_shopify_error(rep)

                if 'Invalid API key or access token' in shopify_error:
                    print u'SHOPIFY EXPORT: {} - Store: {} - Link: {}'.format(
                        shopify_error, store, store.get_link('/admin/products.json', api=True)
                    ).encode('utf-8')
                else:
                    print u'SHOPIFY EXPORT: {} - Store: {}'.format(shopify_error, store).encode('utf-8')

                if 'requires write_products scope' in shopify_error:
                    return {'error': (u'Shopify Error: {}\n\n'
                                      'Please follow this instructions to resolve this issue:'
                                      '\nhttps://app.shopifiedapp.com/pages/view/15'
                                      ).format(shopify_error)}
                elif 'handle: has already been taken' in shopify_error:
                    return {'error': (u'Shopify Error: {}\n\n'
                                      'Please Change your product title by adding or removing one or more words'
                                      ).format(shopify_error)}
                elif 'Exceeded maximum number of variants allowed' in shopify_error:
                    return {'error': (u'Shopify Error: {}\n\n'
                                      'Shopify will only allow 100 variant combinations per product.\n'
                                      'Please delete some of the Color, Size or an other '
                                      'variant options to meet Shopify\'s requirements.'
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
                    user.can_edit(product)

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

    elif target == 'save-for-later':  # save for later
        if 'product' in req_data:
            # Saved product update
            try:
                product = ShopifyProduct.objects.get(id=req_data['product'])
                user.can_edit(product)

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

        else:  # New product to save

            can_add, total_allowed, user_count = user.models_user.profile.can_add_product()
            if not can_add:
                return {
                    'error': 'Your current plan allow up to %d saved products, currently you have %d saved products.'
                             % (total_allowed, user_count)
                }

            is_active = req_data.get('activate', True)

            try:
                product = ShopifyProduct(store=store, user=user.models_user, data=data, is_active=is_active)
                product.set_original_data(original_data)
                product.notes = req_data.get('notes', '')

                user.can_add(product)

                product.save()

                supplier = product.get_supplier_info()
                product.default_supplier = ProductSupplier.objects.create(
                    store=store,
                    product=product,
                    product_url=original_url,
                    supplier_name=supplier.get('name'),
                    supplier_url=supplier.get('url'),
                    is_default=True
                )

            except PermissionDenied as e:
                raven_client.captureException()
                return {
                    'error': "Add Product: {}".format(e.message)
                }

        product.save()

        utils.smart_board_by_product(user.models_user, product)

        url = '/product/%d' % product.id
        pid = product.id
    else:
        return {
            'error': 'Unknown target {}'.format(target)
        }

    if target == 'shopify':
        record_import_metric(time.time() - start)

    return {
        'product': {
            'url': url,
            'id': pid,
        },
        'target': target
    }


@app.task(base=CaptureFailure, bind=True, ignore_result=True)
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
            shopify_product = cache.get('webhook_order_{}_{}'.format(store_id, shopify_id))

        if shopify_product is None:
            shopify_product = utils.get_shopify_product(store, shopify_id)

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


@app.task(base=CaptureFailure, bind=True, ignore_result=True)
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


@app.task(base=CaptureFailure, ignore_result=True)
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


@app.task(base=CaptureFailure, bind=True, ignore_result=True)
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


@app.task(base=CaptureFailure, bind=True)
def add_ordered_note(self, store_id, order_id, note):
    try:
        store = ShopifyStore.objects.get(id=store_id)

        utils.add_shopify_order_note(store, order_id, note)

    except Exception as e:
        if not self.request.called_directly:
            countdown = retry_countdown('retry_ordered_note_{}'.format(order_id), self.request.retries)
            raise self.retry(exc=e, countdown=countdown, max_retries=3)


@app.task(base=CaptureFailure, ignore_result=True)
def invite_user_to_slack(slack_teams, data):
    for team in slack_teams.split(','):
        utils.slack_invite(data, team=team)


@app.task(base=CaptureFailure, bind=True, ignore_result=True, soft_time_limit=600)
def generate_feed(self, feed_id, nocache=False, by_fb=False):
    try:
        feed = FeedStatus.objects.get(id=feed_id)
        generate_product_feed(feed, nocache=nocache)

    except:
        feed.status = 0
        feed.generation_time = -1
        feed.save()

        raven_client.captureException()


@app.task(base=CaptureFailure, ignore_result=True)
def product_change_alert(change_id):
    try:
        product_change = AliexpressProductChange.objects.get(pk=change_id)
        product_change_event = product_alerts_events.ProductChangeEvent(product_change)
        product_change_event.take_action()

    except:
        raven_client.captureException()


@app.task(base=CaptureFailure, bind=True, ignore_result=True)
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
