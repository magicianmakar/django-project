import re
import simplejson as json

from django.conf import settings
from django.views.generic import View

from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.exceptions import ProductExportException
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import safeInt, remove_link_query
from shopified_core import permissions

import tasks
from .models import (
    CommerceHQStore,
    CommerceHQProduct,
    CommerceHQSupplier
)


class CHQStoreApi(ApiResponseMixin, View):
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
            res = self.api_error('zInternal Server Error', 500)

        return res

    def post_product_save(self, request, user, data):
        return self.api_success(tasks.product_save(data, user.id))

    def post_save_for_later(self, request, user, data):
        # Backward compatibly with Shopify save for later
        return self.post_product_save(request, user, data)

    def post_product_export(self, request, user, data):
        try:
            store = CommerceHQStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

            tasks.product_export.apply_async(
                args=[data.get('store'), data.get('product'), user.id],
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
            product = CommerceHQProduct.objects.get(id=data.get('product'))
            permissions.user_can_edit(user, product)

            product_data = json.loads(data['data'])

            tasks.product_update.apply_async(
                args=[product.id, product_data],
                countdown=0,
                expires=60)

            return self.api_success()

        except ProductExportException as e:
            return self.api_error(e.message)

    def post_supplier(self, request, user, data):
        product = CommerceHQProduct.objects.get(id=data.get('product'))
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
            return self.api_error('CommerceHQ store not found', status=500)

        try:
            product_supplier = CommerceHQSupplier.objects.get(id=data.get('export'), store__in=user.profile.get_chq_stores())

            product_supplier.product = product
            product_supplier.product_url = original_link
            product_supplier.supplier_name = data.get('supplier-name')
            product_supplier.supplier_url = supplier_url
            product_supplier.save()

        except (ValueError, CommerceHQSupplier.DoesNotExist):
            product_supplier = CommerceHQSupplier.objects.create(
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
        product = CommerceHQProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        try:
            supplier = CommerceHQSupplier.objects.get(id=data.get('export'), product=product)
        except CommerceHQSupplier.DoesNotExist:
            return self.api_error('Supplier not found.\nPlease reload the page and try again.')

        product.set_default_supplier(supplier, commit=True)

        return self.api_success()

    def post_commercehq_products(self, request, user, data):
        store = safeInt(data.get('store'))
        if not store:
            return self.api_error('No Store was selected', status=404)

        try:
            store = CommerceHQStore.objects.get(id=store)
            permissions.user_can_view(user, store)

            page = safeInt(data.get('page'), 1)
            limit = 25

            params = {
                'fields': 'id,title,images',
                'expand': 'images',
                'limit': limit,
                'page': page
            }

            query = {}
            ids = re.findall('id=([0-9]+)', data.get('query'))
            if ids:
                query['id'] = [ids]
            else:
                query['title'] = data.get('query')

            rep = store.request.post(
                url=store.get_api_url('products/search', api=True),
                params=params,
                json=query
            )

            if not rep.ok:
                return self.api_error('CommerceHQ API Error', status=500)

            products = []
            for i in rep.json()['items']:
                if i.get('images'):
                    i['image'] = {
                        'src': i['images'][0]['path']
                    }

                products.append(i)

            return self.api_success({
                'products': products,
                'page': page,
                'next': page + 1 if len(products) == limit else None,
            })

        except CommerceHQStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

    def post_product_connect(self, request, user, data):
        product = CommerceHQProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        store = CommerceHQStore.objects.get(id=data.get('store'))
        permissions.user_can_view(user, store)

        source_id = safeInt(data.get('shopify'))

        if source_id != product.source_id or product.store != store:
            connected_to = CommerceHQProduct.objects.filter(
                store=store,
                source_id=source_id
            )

            if connected_to.exists():
                return self.api_error(
                    '\n'.join(
                        ['The selected Product is already connected to:\n'] +
                        [request.build_absolute_uri('/chq/product/{}'.format(i))
                            for i in connected_to.values_list('id', flat=True)]),
                    status=500)

            product.store = store
            product.source_id = source_id

            product.save()

            # tasks.update_shopify_product(product.store.id, source_id, product_id=product.id)

        return self.api_success()

    def delete_product_connect(self, request, user, data):
        product = CommerceHQProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        source_id = product.source_id
        if source_id:
            product.source_id = 0
            product.save()

        return self.api_success()
