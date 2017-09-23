import re
import urllib
import urlparse
import json

import requests
import arrow

from requests.exceptions import HTTPError
from raven.contrib.django.raven_compat.models import client as raven_client

from django.views.generic import View
from django.core import serializers
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.urlresolvers import reverse
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.db.models import F

from shopified_core.exceptions import ProductExportException
from shopified_core.mixins import ApiResponseMixin
from shopified_core import permissions
from shopified_core.utils import (
    safeInt,
    safeFloat,
    get_domain,
    remove_link_query,
    orders_update_limit,
    version_compare,
    order_phone_number,
)

from .models import WooStore, WooProduct, WooSupplier, WooOrderTrack, WooBoard
import tasks
import utils


class WooStoreApi(ApiResponseMixin, View):
    http_method_names = ['get', 'post', 'delete']

    def dispatch(self, request, *args, **kwargs):
        if request.method.lower() not in self.http_method_names:
            raven_client.captureMessage('Unsupported Request Method', extra={'method': request.method})
            return self.http_method_not_allowed(request, *args, **kwargs)

        return self.proccess_api(request, **kwargs)

    def proccess_api(self, request, target, store_type, version):
        self.target = target
        self.data = self.request_data(request)

        user = self.get_user(request)
        if user:
            raven_client.user_context({
                'id': user.id,
                'username': user.username,
                'email': user.email
            })

            extension_version = request.META.get('HTTP_X_EXTENSION_VERSION')
            if extension_version:
                user.set_config('extension_version', extension_version)

        method_name = self.method_name(request.method, target)
        handler = getattr(self, method_name, None)

        if not handler:
            if settings.DEBUG:
                print 'Method Not Found:', method_name

            raven_client.captureMessage('Non-handled endpoint', extra={'method': method_name})
            return self.api_error('Non-handled endpoint', status=405)

        res = handler(request, user, self.data)
        if res is None:
            res = self.response

        if res is None:
            raven_client.captureMessage('API Response is empty')
            res = self.api_error('Internal Server Error', 500)

        return res

    def validate_store_data(self, data):
        title = data.get('title', '')
        api_url = data.get('api_url', '')
        api_key = data.get('api_key', '')
        api_password = data.get('api_password', '')

        error_messages = []

        if len(title) > WooStore._meta.get_field('title').max_length:
            error_messages.append('Title is too long.')
        if len(api_key) > WooStore._meta.get_field('api_key').max_length:
            error_messages.append('Consumer key is too long')
        if len(api_password) > WooStore._meta.get_field('api_password').max_length:
            error_messages.append('Consumer secret is too long')

        if not api_url:
            error_messages.append('API URL is required')

        if len(api_url) > WooStore._meta.get_field('api_url').max_length:
            error_messages.append('API URL is too long')

        try:
            validate = URLValidator()
            validate(api_url)
        except ValidationError as e:
            error_messages.extend(e)

        return error_messages

    def check_store_credentials(self, store):
        try:
            r = store.wcapi.get('products')
            r.raise_for_status()
        except HTTPError:
            return False

        return True

    def post_store_add(self, request, user, data):
        if user.is_subuser:
            return self.api_error('Sub-Users can not add new stores.', status=401)

        can_add, total_allowed, user_count = permissions.can_add_store(user)

        if not can_add:
            if user.profile.plan.is_free and user.can_trial():
                from shopify_oauth.views import subscribe_user_to_default_plan

                subscribe_user_to_default_plan(user)
            else:
                raven_client.captureMessage(
                    'Add Extra WooCommerce Store',
                    level='warning',
                    extra={
                        'user': user.email,
                        'plan': user.profile.plan.title,
                        'stores': user.profile.get_woo_stores().count()
                    }
                )

                if user.profile.plan.is_free or user.can_trial():
                    return self.api_error('Please Activate your account first by visiting:\n{}').format(
                        request.build_absolute_uri('/user/profile#plan'), status=401)
                else:
                    return self.api_error('Your plan does not support connecting another WooCommerce store. '
                                          'Please contact support@shopifiedapp.com to learn how to connect more stores.')

        error_messages = self.validate_store_data(data)
        if len(error_messages) > 0:
            return self.api_error(' '.join(error_messages), status=400)

        store = WooStore()
        store.user = user.models_user
        store.title = data.get('title', '').strip()
        store.api_url = data.get('api_url', '').strip()
        store.api_key = data.get('api_key', '').strip()
        store.api_password = data.get('api_password', '').strip()

        permissions.user_can_add(user, store)

        if not self.check_store_credentials(store):
            return self.api_error('API credentials is not correct', status=500)

        store.save()

        return self.api_success()

    def post_store_update(self, request, user, data):
        if user.is_subuser:
            raise PermissionDenied()

        pk = int(data.get('id', 0))
        if not pk:
            return self.api_error('Store ID is required.', status=400)

        try:
            store = WooStore.objects.get(pk=pk, user=user.models_user)
        except WooStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        permissions.user_can_edit(user, store)

        error_messages = self.validate_store_data(data)
        if len(error_messages) > 0:
            return self.api_error(' '.join(error_messages), status=400)

        store.title = data.get('title', '').strip()
        store.api_url = data.get('api_url', '').strip()
        store.api_key = data.get('api_key', '').strip()
        store.api_password = data.get('api_password', '').strip()

        if not self.check_store_credentials(store):
            return self.api_error('API credentials is not correct', status=500)

        store.save()

        return self.api_success()

    def get_store(self, request, user, data):
        pk = int(data.get('id', 0))
        if not pk:
            return self.api_error('Store ID is required.', status=400)

        try:
            store = WooStore.objects.get(pk=pk, user=user.models_user)
        except WooStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        permissions.user_can_view(user, store)

        return self.api_success({
            'id': store.id,
            'title': store.title,
            'api_url': store.api_url,
            'api_key': store.api_key,
            'api_password': store.api_password,
        })

    def delete_store(self, request, user, data):
        if user.is_subuser:
            raise PermissionDenied()

        pk = int(data.get('id', 0))
        if not pk:
            return self.api_error('Store ID is required.', status=400)

        try:
            store = WooStore.objects.get(pk=pk)
        except WooStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        permissions.user_can_delete(user, store)
        store.is_active = False
        store.save()

        return self.api_success()

    def post_product_save(self, request, user, data):
        return self.api_success(tasks.product_save(data, user.id))

    def post_save_for_later(self, request, user, data):
        # Backward compatibly with Shopify save for later
        return self.post_product_save(request, user, data)

    def post_woocommerce_products(self, request, user, data):
        store = safeInt(data.get('store'))
        if not store:
            return self.api_error('No store was selected', status=404)
        try:
            store = WooStore.objects.get(id=store)
            permissions.user_can_view(user, store)
            page = safeInt(data.get('page'), 1)
            limit = 25
            params = {'per_page': limit, 'page': page}

            if data.get('query'):
                params['search'] = data['query']

            try:
                r = store.wcapi.get('products?{}'.format(urllib.urlencode(params)))
                r.raise_for_status()
            except HTTPError:
                return self.api_error('WooCommerce API Error', status=500)

            products = []
            for product in r.json():
                if product.get('images'):
                    product['image'] = {'src': product['images'][0]['src']}
                products.append(product)

            return self.api_success({
                'products': products,
                'page': page,
                'next': page + 1 if len(products) == limit else None})

        except WooStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

    def post_import_product(self, request, user, data):
        try:
            store = WooStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)
        except WooStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)
        if not can_add:
            return self.api_error(
                'Your current plan allow up to %d saved products, currently you have %d saved products.'
                % (total_allowed, user_count), status=401)

        source_id = safeInt(data.get('product'))
        supplier_url = data.get('supplier')

        if source_id:
            if user.models_user.wooproduct_set.filter(source_id=source_id).count():
                return self.api_error('Product is already import/connected', status=422)
        else:
            return self.api_error('WooCommerce Product ID is missing', status=422)

        if not supplier_url:
            return self.api_error('Supplier URL is missing', status=422)

        if get_domain(supplier_url, True) == 'aliexpress':
            if '/deep_link.htm' in supplier_url.lower():
                supplier_url = urlparse.parse_qs(urlparse.urlparse(supplier_url).query)['dl_target_url'].pop()

            if 's.aliexpress.com' in supplier_url.lower():
                rep = requests.get(supplier_url, allow_redirects=False)
                rep.raise_for_status()

                supplier_url = rep.headers.get('location')

                if '/deep_link.htm' in supplier_url:
                    raven_client.captureMessage(
                        'Deep link in redirection',
                        level='warning',
                        extra={
                            'location': supplier_url,
                            'supplier_url': data.get('supplier')
                        })

            supplier_url = remove_link_query(supplier_url)

        product = WooProduct(
            store=store,
            user=user.models_user,
            source_id=source_id,
            data=json.dumps({
                'title': 'Importing...',
                'variants': [],
                'vendor': data.get('vendor_name', 'Supplier'),
                'original_url': supplier_url
            })
        )

        permissions.user_can_add(user, product)

        with transaction.atomic():
            product.save()

            supplier = WooSupplier.objects.create(
                store=product.store,
                product=product,
                product_url=supplier_url,
                supplier_name=data.get('vendor_name', 'Supplier'),
                supplier_url=data.get('vendor_url', 'http://www.aliexpress.com/'),
                is_default=True
            )

            product.set_default_supplier(supplier, commit=True)
            product.sync()

        return self.api_success({'product': product.id})

    def get_product_woocommerce_id(self, request, user, data):
        product = data.get('product').split(',')
        product_ids = [int(id) for id in product]
        ids = WooProduct.objects.filter(user=user.models_user, pk__in=product_ids) \
                                .distinct() \
                                .values_list('source_id', flat=True)

        return self.api_success({'ids': list(ids)})

    def post_product_edit(self, request, user, data):
        products = []
        for p in data.getlist('products[]'):
            product = WooProduct.objects.get(id=p)
            permissions.user_can_edit(user, product)

            product_data = json.loads(product.data)

            if 'tags' in data:
                product_data['tags'] = data.get('tags')

            if 'price' in data:
                product_data['price'] = safeFloat(data.get('price'))

            if 'compare_at' in data:
                product_data['compare_at_price'] = safeFloat(data.get('compare_at'))

            if 'weight' in data:
                product_data['weight'] = data.get('weight')

            if 'weight_unit' in data:
                product_data['weight_unit'] = data.get('weight_unit')

            products.append(product_data)

            product.data = json.dumps(product_data)
            product.save()

        return self.api_success({'products': products})

    def delete_product(self, request, user, data):
        try:
            pk = safeInt(data.get('product'))
            product = WooProduct.objects.get(pk=pk)
            permissions.user_can_delete(user, product)

        except WooProduct.DoesNotExist:
            return self.api_error('Product does not exists', status=404)

        if not user.can('delete_products.sub', product.store):
            raise PermissionDenied()

        product.delete()

        return self.api_success()

    def post_product_export(self, request, user, data):
        try:
            store = WooStore.objects.get(pk=safeInt(data.get('store')))
        except WooStore.DoesNotExist:
            return self.api_error('Store does not exist')
        else:
            permissions.user_can_view(user, store)

        try:
            product = WooProduct.objects.get(pk=safeInt(data.get('product')))
        except WooProduct.DoesNotExist:
            return self.api_error('Product does not exist')
        else:
            permissions.user_can_view(user, product)

        try:
            publish = data.get('publish')
            publish = publish if publish is None else publish == 'true'
            args = [store.id, product.id, user.id, publish]
            tasks.product_export.apply_async(args=args, countdown=0, expires=120)
        except ProductExportException as e:
            return self.api_error(e.message)
        else:
            pusher = {'key': settings.PUSHER_KEY, 'channel': store.pusher_channel()}
            return self.api_success({'pusher': pusher})

    def post_product_update(self, request, user, data):
        try:
            pk = safeInt(data.get('product', 0))
            product = WooProduct.objects.get(pk=pk)
            permissions.user_can_edit(user, product)
            product_data = json.loads(data['data'])
            args = product.id, product_data
            tasks.product_update.apply_async(args=args, countdown=0, expires=60)

            return self.api_success()

        except ProductExportException as e:
            return self.api_error(e.message)

    def post_variants_mapping(self, request, user, data):
        product = WooProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)
        supplier = product.get_suppliers().get(id=data.get('supplier'))
        mapping = {key: value for key, value in data.items() if key not in ['product', 'supplier']}
        product.set_variant_mapping(mapping, supplier=supplier)
        product.save()

        return self.api_success()

    def post_suppliers_mapping(self, request, user, data):
        product = WooProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        suppliers_cache = {}

        mapping = {}
        shipping_map = {}

        with transaction.atomic():
            for k in data:
                if k.startswith('shipping_'):  # Save the shipping mapping for this supplier
                    shipping_map[k.replace('shipping_', '')] = json.loads(data[k])
                elif k.startswith('variant_'):  # Save the varinat mapping for supplier+variant
                    supplier_id, variant_id = k.replace('variant_', '').split('_')
                    supplier = suppliers_cache.get(supplier_id, product.get_suppliers().get(id=supplier_id))

                    suppliers_cache[supplier_id] = supplier
                    var_mapping = {variant_id: data[k]}

                    product.set_variant_mapping(var_mapping, supplier=supplier, update=True)

                elif k == 'config':
                    product.set_mapping_config({'supplier': data[k]})

                elif k != 'product':  # Save the variant -> supplier mapping
                    mapping[k] = json.loads(data[k])

            product.set_suppliers_mapping(mapping)
            product.set_shipping_mapping(shipping_map)
            product.save()

        return self.api_success()

    def post_product_notes(self, request, user, data):
        product = WooProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        product.notes = data.get('notes')
        product.save()

        return self.api_success()

    def post_supplier(self, request, user, data):
        product = WooProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        original_link = remove_link_query(data.get('original-link'))
        supplier_url = remove_link_query(data.get('supplier-link'))

        if 'click.aliexpress.com' in original_link.lower():
            return self.api_error('The submitted Aliexpress link will not work properly with order fulfillment')

        if not original_link:
            return self.api_error('Original Link is not set', status=500)

        try:
            store = product.store
        except:
            store = None

        if not store:
            return self.api_error('WooCommerce store not found', status=500)

        try:
            product_supplier = WooSupplier.objects.get(id=data.get('export'), store__in=user.profile.get_woo_stores())

            product_supplier.product = product
            product_supplier.product_url = original_link
            product_supplier.supplier_name = data.get('supplier-name')
            product_supplier.supplier_url = supplier_url
            product_supplier.save()

        except (ValueError, WooSupplier.DoesNotExist):
            product_supplier = WooSupplier.objects.create(
                store=store,
                product=product,
                product_url=original_link,
                supplier_name=data.get('supplier-name'),
                supplier_url=supplier_url,
            )

        if not product.default_supplier_id or not data.get('export'):
            product.set_default_supplier(product_supplier)

        product.save()

        return self.api_success({'reload': not data.get('export')})

    def post_supplier_default(self, request, user, data):
        product = WooProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        try:
            supplier = WooSupplier.objects.get(id=data.get('export'), product=product)
        except WooSupplier.DoesNotExist:
            return self.api_error('Supplier not found.\nPlease reload the page and try again.')

        product.set_default_supplier(supplier, commit=True)

        return self.api_success()

    def post_variant_image(self, request, user, data):
        store_id = safeInt(data.get('store'))
        product_id = safeInt(data.get('product'))
        variant_id = safeInt(data.get('variant'))
        image_id = safeInt(data.get('image'))

        try:
            store = WooStore.objects.get(id=store_id)
            permissions.user_can_view(user, store)
        except WooStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        try:
            product = WooProduct.objects.get(source_id=product_id)
            permissions.user_can_edit(user, product)
        except WooProduct.DoesNotExist:
            return self.api_error('Product not found', status=404)

        path = 'products/{}/variations/{}'.format(product_id, variant_id)
        data = {'image': {'id': image_id}}
        r = store.wcapi.put(path, data)
        r.raise_for_status()

        return self.api_success()

    def get_product_image_download(self, request, user, data):
        try:
            product = WooProduct.objects.get(id=safeInt(data.get('product')))
            permissions.user_can_view(user, product)

        except WooProduct.DoesNotExist:
            return self.api_error('Product not found', status=404)

        images = product.parsed.get('images')
        if not images:
            return self.api_error('Product doesn\'t have any images', status=422)

        tasks.create_image_zip.delay(images, product.id)

        return self.api_success()

    def post_product_duplicate(self, request, user, data):
        pk = safeInt(data.get('product'))
        product = WooProduct.objects.get(pk=pk)
        permissions.user_can_view(user, product)
        duplicate_product = utils.duplicate_product(product)

        return self.api_success({
            'product': {
                'id': duplicate_product.id,
                'url': reverse('woo:product_detail', args=[duplicate_product.id])
            }
        })

    def post_product_split_variants(self, request, user, data):
        product = WooProduct.objects.get(id=data.get('product'))
        split_factor = data.get('split_factor')
        permissions.user_can_view(user, product)
        splitted_products = utils.split_product(product, split_factor)

        return self.api_success({'products_ids': [p.id for p in splitted_products]})

    def post_fulfill_order(self, request, user, data):
        try:
            store = WooStore.objects.get(id=data.get('fulfill-store'))
        except WooStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        permissions.user_can_view(user, store)
        tracking_number = data.get('fulfill-tracking-number', '')
        provider_id = int(data.get('fulfill-provider', 0))
        tracking_link = data.get('fulfill-tracking-link', '')
        order_id = int(data['fulfill-order-id'])
        line_id = int(data['fulfill-line-id'])
        product_id = int(data['fulfill-product-id'])
        date_shipped = data.get('fulfill-date-shipped')
        provider_name = utils.get_shipping_carrier_name(store, provider_id)

        if provider_name == 'Custom Provider':
            provider_name = data.get('fulfill-provider-name', provider_name)
        if not provider_name:
            return self.api_error('Invalid shipping provider')

        if tracking_link:
            try:
                validate = URLValidator()
                validate(tracking_link)
            except ValidationError as e:
                return self.api_error(','.join(e))

        line_items = [{
            'id': line_id,
            'product_id': product_id,
            'meta_data': [
                {'key': 'Fulfillment Status', 'value': 'Fulfilled'},
                {'key': 'Provider', 'value': provider_name},
                {'key': 'Tracking Number', 'value': tracking_number},
                {'key': 'Tracking Link', 'value': tracking_link},
                {'key': 'Date Shipped', 'value': date_shipped},
            ]
        }]

        try:
            r = store.wcapi.put('orders/{}'.format(order_id), {'line_items': line_items})
            r.raise_for_status()
        except:
            raven_client.captureException(level='warning', extra={'response': r.text})
            return self.api_error('WooCommerce API Error')

        return self.api_success()

    def get_order_fulfill(self, request, user, data):
        if int(data.get('count', 0)) >= 30:
            raise self.api_error('Not found', status=404)

        # Get Orders marked as Ordered

        orders = []

        all_orders = data.get('all') == 'true'
        unfulfilled_only = data.get('unfulfilled_only') != 'false'

        woocommerce_orders = WooOrderTrack.objects.filter(user=user.models_user, hidden=False) \
                                                  .defer('data') \
                                                  .order_by('updated_at')

        if unfulfilled_only:
            woocommerce_orders = woocommerce_orders.filter(source_tracking='') \
                                                   .exclude(source_status='FINISH')

        if user.is_subuser:
            woocommerce_orders = woocommerce_orders.filter(store__in=user.profile.get_woo_stores(flat=True))

        if data.get('store'):
            woocommerce_orders = woocommerce_orders.filter(store=data.get('store'))

        if not data.get('order_id') and not data.get('line_id') and not all_orders:
            limit_key = 'order_fulfill_limit_%d' % user.models_user.id
            limit = cache.get(limit_key)

            if limit is None:
                limit = orders_update_limit(orders_count=woocommerce_orders.count())

                if limit != 20:
                    cache.set(limit_key, limit, timeout=3600)

            if data.get('forced') == 'true':
                limit = limit * 2

            woocommerce_orders = woocommerce_orders[:limit]

        elif data.get('all') == 'true':
            woocommerce_orders = woocommerce_orders.order_by('created_at')

        if data.get('order_id') and data.get('line_id'):
            woocommerce_orders = woocommerce_orders.filter(order_id=data.get('order_id'), line_id=data.get('line_id'))

        if data.get('count_only') == 'true':
            return self.api_success({'pending': woocommerce_orders.count()})

        woocommerce_orders = serializers.serialize('python', woocommerce_orders,
                                                   fields=('id', 'order_id', 'line_id',
                                                           'source_id', 'source_status',
                                                           'source_tracking', 'created_at'))

        for i in woocommerce_orders:
            fields = i['fields']
            fields['id'] = i['pk']

            if all_orders:
                fields['created_at'] = arrow.get(fields['created_at']).humanize()

            orders.append(fields)

        if not data.get('order_id') and not data.get('line_id'):
            WooOrderTrack.objects.filter(user=user.models_user, id__in=[i['id'] for i in orders]) \
                                 .update(check_count=F('check_count') + 1, updated_at=timezone.now())

        return self.api_success(orders, safe=False)

    def post_order_fulfill(self, request, user, data):
        try:
            store = WooStore.objects.get(id=int(data.get('store')))
        except WooStore.DoesNotExist:
            raven_client.captureException()
            return self.api_error('Store {} not found'.format(data.get('store')), status=404)

        if not user.can('place_orders.sub', store):
            raise PermissionDenied()

        permissions.user_can_view(user, store)

        order_id = data.get('order_id')
        line_id = data.get('line_id')
        product_id = data.get('product_id')
        source_id = data.get('aliexpress_order_id')

        if not (order_id and line_id and product_id):
            return self.api_error('Required input is missing')

        try:
            assert len(source_id) > 0, 'Empty Order ID'
            assert utils.safeInt(order_id), 'Order ID is not a numeric'
            source_id.encode('ascii')
        except AssertionError as e:
            raven_client.captureMessage('Non valid Aliexpress Order ID')
            return self.api_error(e.message, status=501)
        except UnicodeEncodeError as e:
            return self.api_error('Order ID is not a valid', status=501)

        tracks = WooOrderTrack.objects.filter(store=store,
                                              order_id=order_id,
                                              line_id=line_id,
                                              product_id=product_id)
        tracks_count = tracks.count()

        if tracks_count > 1:
            extra = {
                'store': store.title,
                'order_id': order_id,
                'line_id': line_id,
                'count': tracks_count}

            raven_client.captureMessage('More Than One Order Track', level='warning', extra=extra)
            tracks.delete()

        if tracks_count == 1:
            saved_track = tracks.first()

            if saved_track.source_id and source_id != saved_track.source_id:
                extra = {
                    'store': store.title,
                    'order_id': order_id,
                    'line_id': line_id,
                    'old': {
                        'id': saved_track.source_id,
                        'date': arrow.get(saved_track.created_at).humanize(),
                    },
                    'new': source_id,
                }
                raven_client.captureMessage('Possible Double Order', level='warning', extra=extra)
                return self.api_error('This Order already have an Aliexpress Order ID', status=422)

        seen_source_orders = WooOrderTrack.objects.filter(store=store, source_id=source_id)
        seen_source_orders = seen_source_orders.values_list('order_id', flat=True)

        if len(seen_source_orders) and int(order_id) not in seen_source_orders and not data.get('forced'):
            extra = {
                'store': store.title,
                'order_id': order_id,
                'line_id': line_id,
                'source_id': source_id,
                'seen_source_orders': list(seen_source_orders)}

            raven_client.captureMessage('Linked to an other Order', level='warning', extra=extra)
            return self.api_error('Aliexpress Order ID is linked to an other Order', status=422)

        track, created = WooOrderTrack.objects.update_or_create(
            store=store,
            order_id=order_id,
            line_id=line_id,
            product_id=product_id,
            defaults={
                'user': user.models_user,
                'source_id': source_id,
                'created_at': timezone.now(),
                'updated_at': timezone.now(),
                'status_updated_at': timezone.now()})

        store.pusher_trigger('order-source-id-add', {
            'track': track.id,
            'order_id': order_id,
            'line_id': line_id,
            'product_id': product_id,
            'source_id': source_id})

        return self.api_success()

    def post_order_fullfill_hide(self, request, user, data):
        order = WooOrderTrack.objects.get(id=data.get('order'))
        permissions.user_can_edit(user, order)

        order.hidden = data.get('hide') == 'true'
        order.save()

        return self.api_success()

    def post_order_fulfill_update(self, request, user, data):
        if data.get('store'):
            store = WooStore.objects.get(pk=safeInt(data['store']))
            if not user.can('place_orders.sub', store):
                raise PermissionDenied()

        order = WooOrderTrack.objects.get(id=data.get('order'))
        permissions.user_can_edit(user, order)

        order.source_status = data.get('status')
        order.source_tracking = re.sub(r'[\n\r\t]', '', data.get('tracking_number')).strip()
        order.status_updated_at = timezone.now()

        try:
            order_data = json.loads(order.data)
            if 'aliexpress' not in order_data:
                order_data['aliexpress'] = {}
        except:
            order_data = {'aliexpress': {}}

        order_data['aliexpress']['end_reason'] = data.get('end_reason')

        try:
            order_data['aliexpress']['order_details'] = json.loads(data.get('order_details'))
        except:
            pass

        order.data = json.dumps(order_data)

        order.save()

        return self.api_success()

    def delete_order_fulfill(self, request, user, data):
        order_id, line_id = int(data.get('order_id')), int(data.get('line_id'))
        orders = WooOrderTrack.objects.filter(user=user.models_user,
                                              order_id=order_id,
                                              line_id=line_id)
        if not len(orders) > 0:
            return self.api_error('Order not found.', status=404)

        for order in orders:
            permissions.user_can_delete(user, order)
            order.delete()
            store, order_id, line_id = order.store, order.order_id, order.line_id
            data = {'store_id': store.id, 'order_id': order_id, 'line_id': line_id}
            store.pusher_trigger('order-source-id-delete', data)

        return self.api_success()

    def post_boards_add(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        can_add, total_allowed, user_count = permissions.can_add_board(user)

        if not can_add:
            return self.api_error(
                'Your current plan allow up to %d boards, currently you have %d boards.'
                % (total_allowed, user_count))

        board_name = data.get('title', '').strip()

        if not len(board_name):
            return self.api_error('Board name is required', status=501)

        board = WooBoard(title=board_name, user=user.models_user)
        permissions.user_can_add(user, board)
        board.save()

        return self.api_success({'board': {'id': board.id, 'title': board.title}})

    def get_board_config(self, request, user, data):
        if not user.can('view_product_boards.sub'):
            raise PermissionDenied()

        try:
            pk = safeInt(data.get('board_id'))
            board = WooBoard.objects.get(pk=pk)
        except WooBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)
        else:
            permissions.user_can_edit(user, board)

        try:
            config = json.loads(board.config)
        except:
            config = {'title': '', 'tags': '', 'type': ''}

        return self.api_success({'title': board.title, 'config': config})

    def post_board_config(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        try:
            pk = safeInt(data.get('board_id'))
            board = WooBoard.objects.get(pk=pk)
        except WooBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)
        else:
            permissions.user_can_edit(user, board)

        board.title = data.get('title')
        board.config = json.dumps({
            'title': data.get('product_title'),
            'tags': data.get('product_tags'),
            'type': data.get('product_type')})
        board.save()

        utils.smart_board_by_board(user.models_user, board)

        return self.api_success()

    def delete_board(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        try:
            pk = safeInt(data.get('board_id'))
            board = WooBoard.objects.get(pk=pk)
        except WooBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)
        else:
            permissions.user_can_delete(user, board)
            board.delete()
            return self.api_success()

    def post_board_empty(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        try:
            pk = safeInt(data.get('board_id'))
            board = WooBoard.objects.get(pk=pk)
        except WooBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)
        else:
            permissions.user_can_edit(user, board)
            board.products.clear()
            return self.api_success()

    def get_products_info(self, request, user, data):
        products = {}
        for p in data.getlist('products[]'):
            pk = safeInt(p)
            try:
                product = WooProduct.objects.get(pk=pk)
            except WooProduct.DoesNotExist:
                return self.api_error('Product not found')
            else:
                permissions.user_can_view(user, product)
                products[p] = json.loads(product.data)

        return self.api_success({'products': products})

    def delete_board_products(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        try:
            pk = safeInt(data.get('board_id'))
            board = WooBoard.objects.get(pk=pk)
        except WooBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)
        else:
            permissions.user_can_edit(user, board)

        for p in data.getlist('products[]'):
            pk = safeInt(p)
            product = WooProduct.objects.filter(pk=pk).first()
            if product:
                permissions.user_can_edit(user, product)
                board.products.remove(product)

        return self.api_success()

    def post_board_add_products(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        try:
            pk = safeInt(data.get('board'))
            board = WooBoard.objects.get(pk=pk)
        except WooBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)
        else:
            permissions.user_can_edit(user, board)

        for p in data.getlist('products[]'):
            pk = safeInt(p)
            product = WooProduct.objects.filter(pk=pk).first()
            if product:
                permissions.user_can_edit(user, product)
                board.products.add(product)

        board.save()

        return self.api_success()

    def post_product_board(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        product = WooProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        if data.get('board') == '0':
            product.wooboard_set.clear()
            product.save()
            return self.api_success()
        else:
            board = WooBoard.objects.get(id=data.get('board'))
            permissions.user_can_edit(user, board)
            board.products.add(product)
            board.save()
            return self.api_success({'board': {'id': board.id, 'title': board.title}})

    def delete_supplier(self, request, user, data):
        product = WooProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        try:
            supplier = WooSupplier.objects.get(id=data.get('supplier'), product=product)
        except WooSupplier.DoesNotExist:
            return self.api_error('Supplier not found.\nPlease reload the page and try again.')

        need_update = product.default_supplier == supplier

        supplier.delete()

        if need_update:
            other_supplier = product.get_suppliers().first()
            if other_supplier:
                product.set_default_supplier(other_supplier)
                product.save()

        return self.api_success()

    def get_order_data(self, request, user, data):
        version = request.META.get('HTTP_X_EXTENSION_VERSION')
        if version:
            required = None

            if version_compare(version, '1.25.6') < 0:
                required = '1.25.6'
            elif version_compare(version, '1.26.0') == 0:
                required = '1.26.1'

            if required:
                raven_client.captureMessage(
                    'Extension Update Required',
                    level='warning',
                    extra={'current': version, 'required': required})

                return self.api_error('Please Update The Extension To Version %s or Higher' % required, status=501)

        order_key = data.get('order')

        if not order_key.startswith('woo_order_'):
            order_key = 'woo_order_{}'.format(order_key)

        store_type, prefix, store, order, line = order_key.split('_')

        try:
            store = WooStore.objects.get(id=int(store))
        except WooStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        permissions.user_can_view(user, store)

        order = utils.order_data_cache(order_key)
        if order:
            if not order['shipping_address'].get('address2'):
                order['shipping_address']['address2'] = ''

            order['ordered'] = False
            order['fast_checkout'] = user.get_config('_fast_checkout', True)
            order['solve'] = user.models_user.get_config('aliexpress_captcha', False)

            phone = order['order']['phone']

            if type(phone) is dict:
                phone_country, phone_number = order_phone_number(request, user.models_user, phone['number'], phone['country'])
                order['order']['phone'] = phone_number
                order['order']['phoneCountry'] = phone_country

            try:
                order_id, line_id = order['order_id'], order['line_id']
                track = WooOrderTrack.objects.get(store=store, order_id=order_id, line_id=line_id)

                order['ordered'] = {
                    'time': arrow.get(track.created_at).humanize(),
                    'link': request.build_absolute_uri('/orders/track?hidden=2&query={}'.format(order['order_id']))
                }

            except WooOrderTrack.DoesNotExist:
                pass
            except:
                raven_client.captureException()

            return self.api_success(order)
        else:
            return self.api_error('Not found: {}'.format(data.get('order')), status=404)

    def post_order_note(self, request, user, data):
        store = WooStore.objects.get(id=data.get('store'))
        permissions.user_can_view(user, store)
        order_id = safeInt(data['order_id'])
        note = data['note']

        if note == utils.get_latest_order_note(store, order_id):
            return self.api_success()

        if utils.add_woo_order_note(store, order_id, note):
            return self.api_success()
        else:
            return self.api_error('WooCommerce API Error', status=500)
