import os
import requests
import traceback
import time
from celery import Celery
from simplejson import JSONDecodeError

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from raven.contrib.django.raven_compat.models import client as raven_client

from .models import *
import utils

app = Celery('shopified')

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object('django.conf:settings')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task
def export_product(req_data, target, user_id):
    start = time.time()

    store = req_data['store']
    data = req_data['data']
    original_data = req_data.get('original', '')

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

    try:
        try:
            store = ShopifyStore.objects.get(id=store)
        except ValueError:
            raven_client.captureException()

            store = ShopifyStore.objects.get(title=store)

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

        print 'ERROR: STORE PERMSSION FOR {} URL: {}'.format(import_store, original_url)

        return {
            'error': 'Importing from this store ({}) is not included in your current plan.'.format(import_store)
        }

    endpoint = store.get_link('/admin/products.json', api=True)

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
                r = requests.post(endpoint, json=json.loads(data))

                if 'product' in r.json():
                    product_to_map = r.json()['product']

                    try:
                        # Link images with variants
                        mapped = utils.shopify_link_images(store, product_to_map)
                        if mapped:
                            r = mapped
                    except Exception as e:
                        raven_client.captureException()

            if 'product' not in r.json():
                rep = r.json()

                print 'SHOPIFY EXPORT: {}'.format(utils.format_shopify_error(rep))
                return {'error': 'Shopify Error: {}'.format(utils.format_shopify_error(rep))}

        except (JSONDecodeError, requests.exceptions.ConnectTimeout):
            raven_client.captureException()
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
            traceback.print_exc()

            return {'error': 'Shopify API Error'}

        pid = r.json()['product']['id']
        url = store.get_link('/admin/products/{}'.format(pid))

        if target == 'shopify':
            if 'product' in req_data:
                try:
                    product = ShopifyProduct.objects.get(id=req_data['product'])
                    user.can_edit(product)

                    original_url = product.get_original_info().get('url', '')

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

                product.shopify_id = pid
                product.stat = 1
                product.save()
            else:
                product = None

            product_export = ShopifyProductExport(original_url=original_url, shopify_id=pid, store=store)
            product_export.save()

            if product:
                product.shopify_export = product_export
                product.save()
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
            product.stat = 0

        else:  # New product to save

            can_add, total_allowed, user_count = user.models_user.profile.can_add_product()
            if not can_add:
                return {
                    'error': 'Your current plan allow up to %d saved products, currently you have %d saved products.'
                             % (total_allowed, user_count)
                }

            is_active = req_data.get('activate', True)

            try:
                product = ShopifyProduct(store=store, user=user.models_user, data=data,
                                         original_data=original_data, stat=0, is_active=is_active)
                product.notes = req_data.get('notes', '')

                user.can_add(product)

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

    if 'later' not in target:
        print '%s Took: %.02f ms' % (target.replace('-', ' ').title(), time.time() - start)

    return {
        'product': {
            'url': url,
            'id': pid,
        },
        'target': target
    }


@app.task
def smartmemeber_webhook_call(subdomain, data):
    rep = requests.post(
        url='https://api.smartmember.com/transaction?type=jvzoo&subdomain={}'.format(subdomain),
        data=data
    )

    print 'SMARTMEMEBER WEBHOOK: {} {}'.format(rep.status_code, rep.text)
