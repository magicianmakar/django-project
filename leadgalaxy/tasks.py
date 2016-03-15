import os
import requests
import traceback
from celery import Celery

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')

from django.conf import settings
from django.contrib.auth.models import User

from .models import *
import utils

app = Celery('shopified')

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object('django.conf:settings')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

app.conf.update(BROKER_URL=os.environ['REDISCLOUD_URL'],
                CELERY_RESULT_BACKEND=os.environ['REDISCLOUD_URL'],
                CELERY_ACCEPT_CONTENT=['pickle', 'json', 'msgpack', 'yaml'],
                CELERY_REDIS_MAX_CONNECTIONS=10)


@app.task
def export_product(req_data, target, user_id):
    print 'Begin:', target.replace('-', ' ').title()

    store = req_data['store']
    data = req_data['data']
    original_data = req_data.get('original', '')

    user = User.objects.get(id=user_id)

    try:
        store = ShopifyStore.objects.get(id=store, user=user)
    except:
        return {
            'error': 'Selected store (%s) not found for user: %s' % (store, user.username if user else 'None')
        }

    original_url = json.loads(data).get('original_url')
    if not original_url:
        original_url = req_data.get('original_url', '')

    try:
        import_store = re.findall('([^\.]+).com/', original_url.lower())
        if len(import_store):
            import_store = import_store[0]
        else:
            import_store = None
    except:
        print 'original_url:', original_url.lower()
        traceback.print_exc()
        return {
            'error': 'Original URL is not set.'
        }

    if import_store and not user.can('%s_import.use' % import_store):
        return {
            'error': 'Importing from this store is not included in your current plan.'
        }

    endpoint = store.get_link('/admin/products.json', api=True)

    product_data = {}
    if target == 'shopify' or target == 'shopify-update':
        try:
            if target == 'shopify-update':
                product = ShopifyProduct.objects.get(id=req_data['product'], user=user)
                api_data = json.loads(data)
                api_data['product']['id'] = product.get_shopify_id()

                update_endpoint = store.get_link('/admin/products/{}.json'.format(product.get_shopify_id()), api=True)
                r = requests.put(update_endpoint, json=api_data)
            else:
                r = requests.post(endpoint, json=json.loads(data))
                product_to_map = r.json()['product']

                try:
                    # Link images with variants
                    mapped = utils.shopify_link_images(store, product_to_map)
                    if mapped:
                        r = mapped
                except Exception as e:
                    traceback.print_exc()

            product_data = r.json()['product']
        except:
            traceback.print_exc()
            print '-----'
            try:
                print r.text
                print '-----'
            except:
                pass

            try:
                d = r.json()
                return {'error': '[Shopify API Error] ' + ' | '.join([k + ': ' + ''.join(d['errors'][k]) for k in d['errors']])}
            except:
                return {'error': 'Shopify API Error'}

        pid = r.json()['product']['id']
        url = store.get_link('/admin/products/{}'.format(pid))

        if target == 'shopify':
            if 'product' in req_data:
                try:
                    product = ShopifyProduct.objects.get(id=req_data['product'], user=user)

                    original_info = product.get_original_info()
                    if original_info:
                        original_url = original_info.get('url', '')
                except Exception as e:
                    return {
                        'error': 'Selected product not found ({})'.format(repr(e))
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
                product = ShopifyProduct.objects.get(id=req_data['product'], user=user)
            except:
                return {
                    'error': 'Selected product not found.'
                }

            product.store = store
            product.data = data
            product.stat = 0

        else:  # New product to save

            # Check if the user plan allow more product saving
            total_products = user.profile.plan.products  # -1 mean unlimited
            user_saved_products = user.shopifyproduct_set.count()

            if (total_products > -1) and (user_saved_products + 1 > total_products):
                if not user.can('unlimited_products.use'):
                    return {
                        'error': 'Your current plan allow up to %d saved products, currently you have %d saved products.'
                                 % (total_products, user_saved_products)
                    }

            is_active = req_data.get('activate', True)

            product = ShopifyProduct(store=store, user=user, data=data, original_data=original_data, stat=0,
                                     is_active=is_active)
            product.notes = req_data.get('notes', '')

        product.save()

        utils.smart_board_by_product(user, product)

        url = '/product/%d' % product.id
        pid = product.id
    else:
        return {
            'error': 'Unknown target {}'.format(target)
        }

    return {
        'product': {
            'url': url,
            'id': pid,
        },
        'target': target
    }
