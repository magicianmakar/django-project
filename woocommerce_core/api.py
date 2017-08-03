import urllib
import urlparse
import json

import requests

from requests.exceptions import HTTPError
from raven.contrib.django.raven_compat.models import client as raven_client

from django.views.generic import View
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.urlresolvers import reverse
from django.conf import settings
from django.db import transaction

from shopified_core.exceptions import ProductExportException
from shopified_core.mixins import ApiResponseMixin
from shopified_core import permissions
from shopified_core.utils import (
    safeInt,
    safeFloat,
    get_domain,
    remove_link_query,
)

from .models import WooStore, WooProduct, WooSupplier
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
            store_id = safeInt(data.get('store'))
            store = WooStore.objects.get(pk=store_id)
            permissions.user_can_view(user, store)

            tasks.product_export.apply_async(
                args=[store_id, data.get('product'), user.id, data.get('publish')],
                countdown=0,
                expires=120)

            return self.api_success({
                'pusher': {
                    'key': settings.PUSHER_KEY,
                    'channel': store.pusher_channel()
                }
            })

        except ProductExportException as e:
            return self.api_error(e.message)

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

        return self.api_success({
            'reload': not data.get('export')
        })

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
