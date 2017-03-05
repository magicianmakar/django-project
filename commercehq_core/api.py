import re
import arrow
import simplejson as json

from django.conf import settings
from django.core.cache import cache
from django.views.generic import View
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.exceptions import ProductExportException
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import safeInt, remove_link_query
from shopified_core import permissions

import tasks
from .models import (
    CommerceHQStore,
    CommerceHQProduct,
    CommerceHQSupplier,
    CommerceHQOrderTrack,
    CommerceHQBoard
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

    def post_order_fulfill(self, request, user, data):
        try:
            store = CommerceHQStore.objects.get(id=int(data.get('store')))
            # if not user.can('place_orders.sub', store): # TODO: subuser perms. for CHQ Stores
            #     raise PermissionDenied()

            permissions.user_can_view(user, store)
        except CommerceHQStore.DoesNotExist:
            raven_client.captureException()
            return self.api_error('Store {} not found'.format(data.get('store')), status=404)

        # Mark Order as Ordered
        order_id = data.get('order_id')
        order_lines = data.get('line_id', '')
        source_id = data.get('aliexpress_order_id', '')

        try:
            assert len(source_id) > 0, 'Empty Order ID'
            assert safeInt(order_id), 'Order ID is not a numbers'
            assert safeInt(source_id), 'Aliexpress ID is not a numbers'
            # assert re.match('^[0-9]{10,}$', source_id) is not None, 'Not a valid Aliexpress Order ID: {}'.format(source_id)

            source_id = int(source_id)

        except AssertionError as e:
            raven_client.captureMessage('Non valid Aliexpress Order ID')

            return self.api_error(e.message, status=501)

        note_delay_key = 'chq_store_{}_order_{}'.format(store.id, order_id)
        note_delay = cache.get(note_delay_key, 0)

        for line_id in order_lines.split(','):
            if not line_id:
                return self.api_error('Order Line Was Not Found.', status=501)

            tracks = CommerceHQOrderTrack.objects.filter(
                store=store,
                order_id=order_id,
                line_id=line_id
            )

            tracks_count = tracks.count()

            if tracks_count > 1:
                raven_client.captureMessage('More Than One Order Track', level='warning', extra={
                    'store': store.title,
                    'order_id': order_id,
                    'line_id': line_id,
                    'count': tracks.count()
                })

                tracks.delete()

            elif tracks_count == 1:
                saved_track = tracks.first()

                if saved_track.source_id and source_id != saved_track.source_id:
                    delta = timezone.now() - saved_track.created_at
                    if delta.days < 1:
                        raven_client.captureMessage('Possible Double Order', level='warning', extra={
                            'store': store.title,
                            'order_id': order_id,
                            'line_id': line_id,
                            'old': {
                                'id': saved_track.source_id,
                                'date': arrow.get(saved_track.created_at).humanize(),
                                'delta': delta
                            },
                            'new': source_id,
                        })

            track, created = CommerceHQOrderTrack.objects.update_or_create(
                store=store,
                order_id=order_id,
                line_id=line_id,
                defaults={
                    'user': user.models_user,
                    'source_id': source_id,
                    'created_at': timezone.now(),
                    'updated_at': timezone.now(),
                    'status_updated_at': timezone.now()
                }
            )

            rep = store.request.post(
                url=store.get_api_url('orders', order_id, 'fulfilments'),
                json={
                    "items": [{
                        "id": line_id,
                        "quantity": cache.get('chq_quantity_{}_{}_{}'.format(store.id, order_id, line_id), 0),
                    }]
                }
            )

            if rep.ok:
                for fulfilment in rep.json()['fulfilments']:
                    for item in fulfilment['items']:
                        cache.set('chq_fulfilments_{}_{}_{}'.format(store.id, order_id, item['id']), fulfilment['id'], timeout=3600)

            # CommerceHQOrderTrack.objects.filter(
            #     order__store=store,
            #     order__order_id=order_id,
            #     line_id=line_id
            # ).update(track=track)

            # TODO: add note to CommerceHQ when it's implemented in the API
            # tasks.mark_as_ordered_note.apply_async(
            #     args=[store.id, order_id, line_id, source_id],
            #     countdown=note_delay)

            store.pusher_trigger('order-source-id-add', {
                'track': track.id,
                'order_id': order_id,
                'line_id': line_id,
                'source_id': source_id,
            })

            cache.set(note_delay_key, note_delay + 5, timeout=5)

        return self.api_success()

    def delete_order_fulfill(self, request, user, data):
        order_id = data.get('order_id')
        line_id = data.get('line_id')

        orders = CommerceHQOrderTrack.objects.filter(user=user.models_user, order_id=order_id, line_id=line_id)

        if orders.count():
            for order in orders:
                permissions.user_can_delete(user, order)

                order.store.request.patch(
                    url=order.store.get_api_url('orders', order_id, 'fulfilments'),
                    json=[{
                        "id": cache.get('chq_fulfilments_{}_{}_{}'.format(order.store.id, order_id, line_id)),
                        "items": [{
                            "id": line_id,
                            "quantity": 0,
                        }]
                    }]
                )

                order.delete()

                order.store.pusher_trigger('order-source-id-delete', {
                    'store_id': order.store.id,
                    'order_id': order.order_id,
                    'line_id': order.line_id,
                })

            return self.api_success()
        else:
            return self.api_error('Order not found.', status=404)

    def delete_store(self, request, user, data):
        if user.is_subuser:
            raise PermissionDenied()
        try:
            pk = safeInt(request.GET.get('store_id'))
            store = CommerceHQStore.objects.get(user=user, pk=pk)
            store.is_active = False
            store.save()
            return self.api_success()
        except CommerceHQBoard.DoesNotExist:
            return self.api_error('Store not found.', status=404)

    def delete_board(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()
        try:
            pk = safeInt(request.GET.get('board_id'))
            board = CommerceHQBoard.objects.get(user=user, pk=pk)
            permissions.user_can_delete(user, board)
            board.delete()
            return self.api_success()
        except CommerceHQBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)

    def post_board_empty(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()
        try:
            pk = safeInt(data.get('board_id'))
            board = CommerceHQBoard.objects.get(user=user, pk=pk)
            permissions.user_can_edit(user, board)
            board.products.clear()
            return self.api_success()
        except CommerceHQBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)

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

        board = CommerceHQBoard(title=board_name, user=user.models_user)
        permissions.user_can_add(user, board)

        board.save()

        return self.api_success({
            'board': {
                'id': board.id,
                'title': board.title
            }
        })
