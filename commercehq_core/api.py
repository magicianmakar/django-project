import re
import arrow
import urlparse
import simplejson as json

from django.conf import settings
from django.core import serializers
from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.views.generic import View
from django.utils import timezone
from django.core.exceptions import PermissionDenied

import requests
from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.exceptions import ProductExportException
from shopified_core.mixins import ApiResponseMixin
from shopified_core import permissions
from shopified_core.utils import (
    safeInt,
    get_domain,
    remove_link_query,
    version_compare,
    orders_update_limit,
    order_phone_number
)

import tasks
import utils

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

    def delete_product(self, request, user, data):
        try:
            product = CommerceHQProduct.objects.get(id=data.get('product'))
            permissions.user_can_delete(user, product)
        except CommerceHQProduct.DoesNotExist:
            return self.api_error('Product does not exists', status=404)

        # TODO: Sub user permssion for CHQ
        # if not user.can('delete_products.sub', product.store):
            # raise PermissionDenied()

        product.delete()

        return self.api_success()

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

    def get_order_fulfill(self, request, user, data):
        if int(data.get('count', 0)) >= 30:
            raise self.api_error('Not found', status=404)

        # Get Orders marked as Ordered

        orders = []

        all_orders = data.get('all') == 'true'
        unfulfilled_only = data.get('unfulfilled_only') != 'false'

        shopify_orders = CommerceHQOrderTrack.objects.filter(user=user.models_user, hidden=False) \
                                                     .defer('data') \
                                                     .order_by('updated_at')

        if unfulfilled_only:
            shopify_orders = shopify_orders.filter(source_tracking='') \
                                           .exclude(source_status='FINISH')

        if user.is_subuser:
            shopify_orders = shopify_orders.filter(store__in=user.profile.get_shopify_stores(flat=True))

        if data.get('store'):
            shopify_orders = shopify_orders.filter(store=data.get('store'))

        if not data.get('order_id') and not data.get('line_id') and not all_orders:
            limit_key = 'order_fulfill_limit_%d' % user.models_user.id
            limit = cache.get(limit_key)

            if limit is None:
                limit = orders_update_limit(orders_count=shopify_orders.count())

                if limit != 20:
                    cache.set(limit_key, limit, timeout=3600)

            if data.get('forced') == 'true':
                limit = limit * 2

            shopify_orders = shopify_orders[:limit]

        elif data.get('all') == 'true':
            shopify_orders = shopify_orders.order_by('created_at')

        if data.get('order_id') and data.get('line_id'):
            shopify_orders = shopify_orders.filter(order_id=data.get('order_id'), line_id=data.get('line_id'))

        if data.get('count_only') == 'true':
            return self.api_success({'pending': shopify_orders.count()})

        shopify_orders = serializers.serialize('python', shopify_orders,
                                               fields=('id', 'order_id', 'line_id',
                                                       'source_id', 'source_status',
                                                       'source_tracking', 'created_at'))

        for i in shopify_orders:
            fields = i['fields']
            fields['id'] = i['pk']

            if all_orders:
                fields['created_at'] = arrow.get(fields['created_at']).humanize()

            orders.append(fields)

        if not data.get('order_id') and not data.get('line_id'):
            CommerceHQOrderTrack.objects.filter(user=user.models_user, id__in=[i['id'] for i in orders]) \
                                        .update(check_count=F('check_count') + 1, updated_at=timezone.now())

        return self.api_success(orders, safe=False)

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

        if len(orders):
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

    def post_store_add(self, request, user, data):
        url = data.get('api_url').strip()

        url = re.findall(r'([^/.]+\.commercehq(?:dev)?\.com)', url)

        if len(url):
            url = url.pop()
        else:
            return self.api_error('CommerceHQ stores URL is not correct', status=422)

        if user.is_subuser:
            return self.api_error('Sub-Users can not add new stores.', status=401)

        can_add, total_allowed, user_count = permissions.can_add_store(user)

        if not can_add:
            if user.profile.plan.is_free and user.can_trial():
                from shopify_oauth.views import subscribe_user_to_default_plan

                subscribe_user_to_default_plan(user)
            else:
                raven_client.captureMessage(
                    'Add Extra CHQ Store',
                    level='warning',
                    extra={
                        'user': user.email,
                        'plan': user.profile.plan.title,
                        'stores': user.profile.get_chq_stores().count()
                    }
                )

                if user.profile.plan.is_free or user.can_trial():
                    return self.api_error('Please Activate your account first by visiting:\n{}').format(
                        request.build_absolute_uri('/user/profile#plan'), status=401)
                else:
                    return self.api_error('Your plan does not support connecting another Shopify store. '
                                          'Please contact support@shopifiedapp.com to learn how to connect more stores.')

        store = CommerceHQStore(
            title=data.get('title').strip(),
            api_url=url,
            api_key=data.get('api_key').strip(),
            api_password=data.get('api_password').strip(),
            user=user.models_user)

        permissions.user_can_add(user, store)

        try:
            rep = store.request.get(
                store.get_api_url('products'),
                params={'fields': 'id', 'size': 1}
            )

            rep.raise_for_status()
        except:
            return self.api_error('API credetnails is not correct', status=500)

        store.save()

        return self.api_success()

    def delete_store(self, request, user, data):
        if user.is_subuser:
            raise PermissionDenied()

        try:
            pk = safeInt(data.get('store_id'))
            store = CommerceHQStore.objects.get(user=user, pk=pk)
            store.is_active = False
            store.save()
            return self.api_success()
        except CommerceHQBoard.DoesNotExist:
            return self.api_error('Store not found.', status=404)

    def delete_board(self, request, user, data):
        # if not user.can('edit_product_boards.sub'):
        #     raise PermissionDenied()

        try:
            pk = safeInt(data.get('board_id'))
            board = CommerceHQBoard.objects.get(pk=pk)
            permissions.user_can_delete(user, board)
            board.delete()
            return self.api_success()
        except CommerceHQBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)

    def post_board_empty(self, request, user, data):
        # if not user.can('edit_product_boards.sub'):
        #     raise PermissionDenied()

        try:
            pk = safeInt(data.get('board_id'))
            board = CommerceHQBoard.objects.get(pk=pk)
            permissions.user_can_edit(user, board)
            board.products.clear()
            return self.api_success()
        except CommerceHQBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)

    def post_boards_add(self, request, user, data):
        # if not user.can('edit_product_boards.sub'):
        #     raise PermissionDenied()

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

    def post_product_board(self, request, user, data):
        # if not user.can('edit_product_boards.sub'):
        #     raise PermissionDenied()

        product = CommerceHQProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        if data.get('board') == '0':
            product.commercehqboard_set.clear()
            product.save()

            return self.api_success()
        else:
            board = CommerceHQBoard.objects.get(id=data.get('board'))
            permissions.user_can_edit(user, board)

            board.products.add(product)
            board.save()

            return self.api_success({
                'board': {
                    'id': board.id,
                    'title': board.title
                }
            })

    def get_board_config(self, request, user, data):
        try:
            pk = safeInt(data.get('board_id'))
            board = CommerceHQBoard.objects.get(pk=pk)
            permissions.user_can_edit(user, board)
        except CommerceHQBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)

        try:
            return self.api_success({
                'title': board.title,
                'config': json.loads(board.config)
            })
        except:
            return self.api_success({
                'title': board.title,
                'config': {
                    'title': '',
                    'tags': '',
                    'type': ''
                }
            })

    def post_board_config(self, request, user, data):
        try:
            pk = safeInt(data.get('board_id'))
            board = CommerceHQBoard.objects.get(pk=pk)
            permissions.user_can_edit(user, board)
        except CommerceHQBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)

        board.title = data.get('title')

        board.config = json.dumps({
            'title': data.get('product_title'),
            'tags': data.get('product_tags'),
            'type': data.get('product_type'),
        })

        board.save()

        utils.smart_board_by_board(user.models_user, board)

        return self.api_success()

    def delete_board_products(self, request, user, data):
        # if not user.can('edit_product_boards.sub'):
        #    raise PermissionDenied()
        try:
            pk = safeInt(data.get('board_id'))
            board = CommerceHQBoard.objects.get(pk=pk)
            permissions.user_can_edit(user, board)
        except CommerceHQBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)

        for p in data.getlist('products[]'):
            pk = safeInt(p)
            product = CommerceHQProduct.objects.filter(pk=pk).first()
            if product:
                permissions.user_can_edit(user, product)
                board.products.remove(product)

        return self.api_success()

    def post_product_edit(self, request, user, data):
        products = []
        for p in data.getlist('products[]'):
            product = CommerceHQProduct.objects.get(id=p)
            permissions.user_can_edit(user, product)

            product_data = json.loads(product.data)

            if 'tags' in data:
                product_data['tags'] = data.get('tags')

            if 'price' in data:
                product_data['price'] = utils.safeFloat(data.get('price'))

            if 'compare_at' in data:
                product_data['compare_at_price'] = utils.safeFloat(data.get('compare_at'))

            if 'type' in data:
                product_data['type'] = data.get('type')

            if 'weight' in data:
                product_data['weight'] = data.get('weight')

            if 'weight_unit' in data:
                product_data['weight_unit'] = data.get('weight_unit')

            products.append(product_data)

            product.data = json.dumps(product_data)
            product.save()

        return self.api_success({'products': products})

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

        if not order_key.startswith('order_'):
            order_key = 'order_{}'.format(order_key)

        prefix, store, order, line = order_key.split('_')

        try:
            store = CommerceHQStore.objects.get(id=store)
            permissions.user_can_view(user, store)
        except CommerceHQStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        order = cache.get(order_key)
        if order:
            if not order['shipping_address'].get('address2'):
                order['shipping_address']['address2'] = ''

            order['ordered'] = False
            order['fast_checkout'] = user.get_config('_fast_checkout', False)
            order['solve'] = user.models_user.get_config('aliexpress_captcha', False)

            phone = order['order']['phone']
            if type(phone) is dict:
                phone_country, phone_number = order_phone_number(request, user.models_user, phone['number'], phone['country'])
                order['order']['phone'] = phone_number
                order['order']['phoneCountry'] = phone_country

            try:
                track = CommerceHQOrderTrack.objects.get(
                    store=store,
                    order_id=order['order_id'],
                    line_id=order['line_id']
                )

                order['ordered'] = {
                    'time': arrow.get(track.created_at).humanize(),
                    'link': request.build_absolute_uri('/orders/track?hidden=2&query={}'.format(order['order_id']))
                }

            except CommerceHQOrderTrack.DoesNotExist:
                pass
            except:
                raven_client.captureException()

            return self.api_success(order)
        else:
            return self.api_error('Not found: {}'.format(data.get('order')), status=404)

    def post_order_fulfill_update(self, request, user, data):
        # if data.get('store'):
        #     store = CommerceHQStore.objects.get(pk=int(data['store']))

        #     TODO: sub user permission for CHQ
        #     if not user.can('place_orders.sub', store):
        #         raise PermissionDenied()

        order = CommerceHQOrderTrack.objects.get(id=data.get('order'))
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

    def post_order_fullfill_hide(self, request, user, data):
        order = CommerceHQOrderTrack.objects.get(id=data.get('order'))
        permissions.user_can_edit(user, order)

        order.hidden = data.get('hide') == 'true'
        order.save()

        return self.api_success()

    def post_fulfill_order(self, request, user, data):
        try:
            store = CommerceHQStore.objects.get(id=data.get('fulfill-store'))
            permissions.user_can_view(user, store)

            # if not user.can('place_orders.sub', store):
            #     raise PermissionDenied()
        except CommerceHQStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        fulfillment_data = {
            'store_id': store.id,
            'line_id': int(data.get('fulfill-line-id')),
            'order_id': data.get('fulfill-order-id'),
            'source_tracking': data.get('fulfill-traking-number'),
            'use_usps': data.get('fulfill-tarcking-link') == 'usps',
            'user_config': {
                'send_shipping_confirmation': data.get('fulfill-notify-customer'),
                'validate_tracking_number': False,
                'aftership_domain': user.get_config('aftership_domain', 'track')
            }
        }

        # api_data = utils.order_track_fulfillment(**fulfillment_data)
        api_data = {
            "data": [{
                "fulfilment_id": cache.get('chq_fulfilments_{store_id}_{order_id}_{line_id}'.format(**fulfillment_data)),
                "tracking_number": fulfillment_data['source_tracking'],
                "shipping_carrier": safeInt(data.get('fulfill-tarcking-link'), ''),
                "items": [{
                    "id": fulfillment_data['line_id'],
                    "quantity": cache.get('chq_quantity_{store_id}_{order_id}_{line_id}'.format(**fulfillment_data))
                }]
            }],
            "notify": (data.get('fulfill-notify-customer') == 'yes')
        }

        rep = store.request.post(
            url=store.get_api_url('orders', data.get('fulfill-order-id'), 'shipments'),
            json=api_data
        )

        try:
            rep.raise_for_status()
        except:
            raven_client.captureException(
                level='warning',
                extra={'response': rep.text})

            return self.api_error('CommerceHQ API Error')

        return self.api_success()

    def post_import_product(self, request, user, data):
        try:
            store = CommerceHQStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)
        except CommerceHQStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)
        if not can_add:
            return self.api_error(
                'Your current plan allow up to %d saved products, currently you have %d saved products.'
                % (total_allowed, user_count), status=401)

        source_id = safeInt(data.get('product'))
        supplier_url = data.get('supplier')

        if source_id:
            if user.models_user.commercehqproduct_set.filter(source_id=source_id).count():
                return self.api_error('Product is already import/connected', status=422)
        else:
            return self.api_error('Shopify Product ID is missing', status=422)

        if not supplier_url:
            return self.api_error('Supplier URL is missing', status=422)

        if get_domain(supplier_url) == 'aliexpress':
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

        product = CommerceHQProduct(
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
        product.save()

        supplier = CommerceHQSupplier.objects.create(
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

    def post_variants_mapping(self, request, user, data):
        product = CommerceHQProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        supplier = product.get_suppliers().get(id=data.get('supplier'))

        mapping = {}
        for k in data:
            if k != 'product' and k != 'supplier':
                mapping[k] = data[k]

        if not product.default_supplier:
            supplier = product.get_supplier_info()
            product.default_supplier = CommerceHQSupplier.objects.create(
                store=product.store,
                product=product,
                product_url=product.get_original_info().get('url', ''),
                supplier_name=supplier.get('name'),
                supplier_url=supplier.get('url'),
                is_default=True
            )

            supplier = product.default_supplier

        product.set_variant_mapping(mapping, supplier=supplier)
        product.save()

        return self.api_success()

    def post_suppliers_mapping(self, request, user, data):
        product = CommerceHQProduct.objects.get(id=data.get('product'))
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

    def get_product_image_download(self, request, user, data):
        try:
            product = CommerceHQProduct.objects.get(id=data.get('product'))
            permissions.user_can_view(user, product)

        except CommerceHQProduct.DoesNotExist:
            return self.api_error('Product not found', status=404)

        images = json.loads(product.data).get('images')
        if not images:
            return self.api_error('Product doesn\'t have any images', status=422)

        tasks.create_image_zip.delay(images, product.id)

        return self.api_success()
