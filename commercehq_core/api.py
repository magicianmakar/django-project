import re
from urllib.parse import parse_qs, urlparse

import simplejson as json
from functools import cmp_to_key

from django.conf import settings
from django.core.cache import cache, caches
from django.utils import timezone
from django.core.exceptions import PermissionDenied

import requests
from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core import permissions
from shopified_core.api_base import ApiBase
from shopified_core.exceptions import ProductExportException
from shopified_core.utils import (
    safe_int,
    get_domain,
    remove_link_query,
    order_data_cache,
    CancelledOrderAlert
)
from product_alerts.utils import unmonitor_store

from supplements.models import SUPPLEMENTS_SUPPLIER, UserSupplement

from . import tasks
from . import utils

from .api_helper import CHQApiHelper
from .models import (
    CommerceHQStore,
    CommerceHQProduct,
    CommerceHQSupplier,
    CommerceHQOrderTrack,
    CommerceHQBoard
)


class CHQStoreApi(ApiBase):
    store_label = 'CommerceHQ'
    store_slug = 'chq'
    board_model = CommerceHQBoard
    product_model = CommerceHQProduct
    order_track_model = CommerceHQOrderTrack
    store_model = CommerceHQStore
    helper = CHQApiHelper()

    def post_save_orders_filter(self, request, user, data):
        utils.set_orders_filter(user, data)
        return self.api_success()

    def post_product_export(self, request, user, data):
        try:
            store = CommerceHQStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

            if not user.can('send_to_chq.sub', store):
                raise PermissionDenied()

            tasks.product_export.apply_async(
                args=[data.get('store'), data.get('product'), user.id, data.get('publish')],
                countdown=0,
                expires=120)

            return self.api_success({
                'pusher': {
                    'key': settings.PUSHER_KEY,
                    'channel': store.pusher_channel()
                }
            })

        except ProductExportException as e:
            return self.api_error(str(e))

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
            return self.api_error(str(e))

    def delete_product(self, request, user, data):
        try:
            product = CommerceHQProduct.objects.get(id=data.get('product'))
            permissions.user_can_delete(user, product)
        except CommerceHQProduct.DoesNotExist:
            return self.api_error('Product does not exists', status=404)

        if not user.can('delete_products.sub', product.store):
            raise PermissionDenied()

        product.delete()

        return self.api_success()

    def post_supplier(self, request, user, data):
        product = CommerceHQProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        original_link = remove_link_query(data.get('original-link'))
        supplier_url = remove_link_query(data.get('supplier-link'))

        if get_domain(original_link) == 'dropified':
            try:
                user_supplement_id = int(urlparse(original_link).path.split('/')[-1])
                user_supplement = UserSupplement.objects.get(id=user_supplement_id)
                product.user_supplement_id = user_supplement
            except:
                raven_client.captureException(level='warning')
                return self.api_error('Product supplier is not correct', status=500)

        elif 'click.aliexpress.com' in original_link.lower():
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

    def delete_supplier(self, request, user, data):
        product = CommerceHQProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        try:
            supplier = CommerceHQSupplier.objects.get(id=data.get('supplier'), product=product)
        except CommerceHQSupplier.DoesNotExist:
            return self.api_error('Supplier not found.\nPlease reload the page and try again.')

        need_update = product.default_supplier == supplier

        supplier.delete()

        if need_update:
            other_supplier = product.get_suppliers().first()
            if other_supplier:
                product.set_default_supplier(other_supplier)
                product.save()

        return self.api_success()

    def post_bundles_mapping(self, request, user, data):
        product = CommerceHQProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        product.set_bundle_mapping(data.get('mapping'))
        product.save()

        return self.api_success()

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
        store = safe_int(data.get('store'))
        if not store:
            return self.api_error('No Store was selected', status=404)

        try:
            store = CommerceHQStore.objects.get(id=store)
            permissions.user_can_view(user, store)

            page = safe_int(data.get('page'), 1)
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

            if data.get('connected') or data.get('hide_connected'):
                connected = {}
                for p in store.products.filter(source_id__in=[i['id'] for i in products]).values_list('id', 'source_id'):
                    connected[p[1]] = p[0]

                for idx, i in enumerate(products):
                    products[idx]['connected'] = connected.get(i['id'])

                def connected_cmp(a, b):
                    if a['connected'] and b['connected']:
                        return a['connected'] < b['connected']
                    elif a['connected']:
                        return 1
                    elif b['connected']:
                        return -1
                    else:
                        return 0

                products = sorted(products, key=cmp_to_key(connected_cmp), reverse=True)

                if data.get('hide_connected'):
                    products = [p for p in products if not p.get('connected')]

            return self.api_success({
                'products': products,
                'page': page,
                'next': page + 1 if len(products) == limit else None,
            })

        except CommerceHQStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

    def post_order_fulfill(self, request, user, data):
        try:
            store = CommerceHQStore.objects.get(id=int(data.get('store')))
            if not user.can('place_orders.sub', store):
                raise PermissionDenied()

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
            source_id.encode('ascii')

        except AssertionError as e:
            raven_client.captureException(level='warning')

            return self.api_error(str(e), status=501)

        except UnicodeEncodeError:
            return self.api_error('Order ID is invalid', status=501)

        note_delay_key = 'chq_store_{}_order_{}'.format(store.id, order_id)
        note_delay = cache.get(note_delay_key, 0)

        order_updater = utils.CHQOrderUpdater(store, order_id)

        if data.get('combined'):
            order_lines = order_lines.split(',')
            current_line = order_data_cache(store.id, order_id, order_lines[0])
            for key, order_data in list(order_data_cache(store.id, order_id, '*').items()):
                if current_line and str(order_data['line_id']) not in order_lines \
                        and str(order_data['source_id']) == str(current_line['source_id']) \
                        and not CommerceHQOrderTrack.objects.filter(store=store, order_id=order_id, line_id=order_data['line_id']).exists():
                    order_lines.append(str(order_data['line_id']))

            order_lines = ','.join(order_lines)

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
                tracks.delete()

            elif tracks_count == 1:
                saved_track = tracks.first()

                if saved_track.source_id and source_id != saved_track.source_id:
                    return self.api_error('This order already has a supplier order ID', status=422)

            seem_source_orders = CommerceHQOrderTrack.objects.filter(
                store=store,
                source_id=source_id
            ).values_list('order_id', flat=True)

            if len(seem_source_orders) and int(order_id) not in seem_source_orders and not data.get('forced'):
                return self.api_error('Supplier order ID is linked to another order', status=409)

            track, created = CommerceHQOrderTrack.objects.update_or_create(
                store=store,
                order_id=order_id,
                line_id=line_id,
                defaults={
                    'user': user.models_user,
                    'source_id': source_id,
                    'source_type': data.get('source_type'),
                    'created_at': timezone.now(),
                    'updated_at': timezone.now(),
                    'status_updated_at': timezone.now()
                }
            )

            try:
                api_data = {
                    "items": [{
                        "id": line_id,
                        "quantity": caches['orders'].get('chq_quantity_{}_{}_{}'.format(store.id, order_id, line_id)) or 1,
                    }]
                }

                rep = store.request.post(
                    url=store.get_api_url('orders', order_id, 'fulfilments'),
                    json=api_data
                )

                rep.raise_for_status()

                for fulfilment in rep.json()['fulfilments']:
                    for item in fulfilment['items']:
                        caches['orders'].set('chq_fulfilments_{}_{}_{}'.format(store.id, order_id, item['id']), fulfilment['id'], timeout=604800)

                profile = user.models_user.profile

                # TODO: Handle multi values in source_id
                if profile.get_config_value('aliexpress_as_notes', True):
                    order_updater.mark_as_ordered_note(line_id, source_id, track)

            except Exception:
                rep = store.request.get(url=store.get_api_url('orders', order_id))
                if rep.ok:
                    for fulfilment in rep.json()['fulfilments']:
                        for item in fulfilment['items']:
                            if item['id'] == int(line_id):
                                caches['orders'].set('chq_fulfilments_{}_{}_{}'.format(
                                    store.id, order_id, item['id']), fulfilment['id'], timeout=604800)

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
                'source_url': track.get_source_url(),
            })

            cache.set(note_delay_key, note_delay + 5, timeout=5)

        if not settings.DEBUG and 'oberlo.com' not in request.META.get('HTTP_REFERER', ''):
            order_updater.delay_save(countdown=note_delay)

        return self.api_success({'order_track_id': track.id})

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
                        "id": caches['orders'].get('chq_fulfilments_{}_{}_{}'.format(order.store.id, order_id, line_id)),
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

        url = re.findall(r'([^/.]+\.commercehq(?:dev|testing)?\.com)', url)

        if len(url):
            url = url.pop()
        else:
            return self.api_error('CommerceHQ stores URL is not correct', status=422)

        if user.is_subuser:
            return self.api_error('Sub-Users can not add new stores.', status=401)

        can_add, total_allowed, user_count = permissions.can_add_store(user)

        if not can_add:
            if user.profile.plan.is_free and user.can_trial() and not user.profile.from_shopify_app_store():
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

                if user.profile.plan.is_free and not user_count:
                    return self.api_error('Please Activate your account first by visiting:\n{}'.format(
                        request.build_absolute_uri('/user/profile#plan')), status=401)
                else:
                    return self.api_error('Your plan does not support connecting another Shopify store. '
                                          'Please contact support@dropified.com to learn how to connect more stores.')

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
            return self.api_error('API Credentials are incorrect', status=500)

        store.save()

        return self.api_success()

    def delete_store(self, request, user, data):
        if user.is_subuser:
            raise PermissionDenied()

        try:
            pk = safe_int(data.get('store_id'))
            store = CommerceHQStore.objects.get(user=user, pk=pk)
            permissions.user_can_delete(user, store)

            store.is_active = False
            store.save()

            unmonitor_store(store)

            return self.api_success()
        except CommerceHQBoard.DoesNotExist:
            return self.api_error('Store not found.', status=404)

    def get_store_verify(self, request, user, data):
        try:
            store = CommerceHQStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except CommerceHQStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        rep = None
        try:
            rep = store.request.get(
                store.get_api_url('products'),
                params={'fields': 'id', 'size': 1}
            )

            rep.raise_for_status()

            return self.api_success({'store': store.get_store_url()})

        except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout):
            return self.api_error('Connection to your store is not successful at:\n{}'.format(store.get_store_url()))

        except IndexError:
            return self.api_error('Your Store link is not correct:\n{}'.format(store.api_url))
        except:
            return self.api_error('API Credentials are incorrect\nError: {}'.format(rep.reason if rep is not None else 'Unknown Issue'))

    def delete_board(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        try:
            pk = safe_int(data.get('board_id'))
            board = CommerceHQBoard.objects.get(pk=pk)
            permissions.user_can_delete(user, board)
            board.delete()
            return self.api_success()
        except CommerceHQBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)

    def post_product_remove_board(self, request, user, data):
        # DEPRECATED
        return self.delete_board_products(request, user, data)

    def post_order_fulfill_update(self, request, user, data):
        if data.get('store'):
            store = CommerceHQStore.objects.get(pk=safe_int(data['store']))
            if not user.can('place_orders.sub', store):
                raise PermissionDenied()

        try:
            order = CommerceHQOrderTrack.objects.get(id=data.get('order'))
            permissions.user_can_edit(user, order)
        except CommerceHQOrderTrack.DoesNotExist:
            return self.api_error('Order Not Found', status=404)

        cancelled_order_alert = CancelledOrderAlert(user.models_user,
                                                    data.get('source_id'),
                                                    data.get('end_reason'),
                                                    order.source_status_details,
                                                    order)

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

        if data.get('bundle') and data['bundle'] != 'false':
            if not order_data.get('bundle'):
                order_data['bundle'] = {}

            if not order_data['bundle'].get(data.get('source_id')):
                order_data['bundle'][data.get('source_id')] = {}

            order_data['bundle'][data.get('source_id')] = {
                'source_status': data.get('status'),
                'source_tracking': data.get('tracking_number'),
                'end_reason': data.get('end_reason'),
                'order_details': json.loads(data.get('order_details')),
            }

        order.data = json.dumps(order_data)

        order.save()

        # Send e-mail notifications for cancelled orders
        cancelled_order_alert.send_email()

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
                'aftership_domain': user.models_user.get_config('aftership_domain', 'track')
            }
        }

        while True:
            # api_data = utils.order_track_fulfillment(**fulfillment_data)
            fulfilment_id = caches['orders'].get('chq_fulfilments_{store_id}_{order_id}_{line_id}'.format(**fulfillment_data))
            if fulfilment_id is None:
                rep = store.request.post(
                    url=store.get_api_url('orders', fulfillment_data['order_id'], 'fulfilments'),
                    json={
                        "items": [{
                            "id": fulfillment_data['line_id'],
                            "quantity": caches['orders'].get('chq_quantity_{store_id}_{order_id}_{line_id}'.format(**fulfillment_data)) or 1,
                        }]
                    }
                )

                if rep.ok:
                    for fulfilment in rep.json()['fulfilments']:
                        for item in fulfilment['items']:
                            caches['orders'].set('chq_fulfilments_{}_{}_{}'.format(store.id, fulfillment_data['order_id'], item['id']),
                                                 fulfilment['id'], timeout=604800)

                    fulfilment_id = caches['orders'].get('chq_fulfilments_{store_id}_{order_id}_{line_id}'.format(**fulfillment_data))
                else:
                    msg = ''
                    if 'Warehouse ID' in rep.text:
                        msg = 'Inventory Tracking is enabled for this product'

                    return self.api_error('CommerceHQ API Error\n{}'.format(msg))

            api_data = {
                "data": [{
                    "fulfilment_id": fulfilment_id,
                    "tracking_number": fulfillment_data['source_tracking'],
                    "shipping_carrier": safe_int(data.get('fulfill-tarcking-link'), ''),
                    "items": [{
                        "id": fulfillment_data['line_id'],
                        "quantity": caches['orders'].get('chq_quantity_{store_id}_{order_id}_{line_id}'.format(**fulfillment_data)) or 1
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

                if fulfilment_id and 'status fulfilled must be no less than' in rep.text.lower():
                    store.request.delete(url=store.get_api_url('orders', fulfillment_data['order_id'], 'fulfilments', fulfilment_id))
                    caches['orders'].delete('chq_fulfilments_{store_id}_{order_id}_{line_id}'.format(**fulfillment_data))
                    continue

                elif 'fulfilment id is invalid' in rep.text.lower():
                    caches['orders'].delete('chq_fulfilments_{store_id}_{order_id}_{line_id}'.format(**fulfillment_data))
                    continue

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

        source_id = safe_int(data.get('product'))
        supplier_url = data.get('supplier')

        if source_id:
            if user.models_user.commercehqproduct_set.filter(store=store, source_id=source_id).count():
                return self.api_error('Product is already imported/connected', status=422)
        else:
            return self.api_error('Shopify Product ID is missing', status=422)

        if not supplier_url:
            return self.api_error('Supplier URL is missing', status=422)

        user_supplement = None
        if get_domain(supplier_url) == 'aliexpress':
            if '/deep_link.htm' in supplier_url.lower():
                supplier_url = parse_qs(urlparse(supplier_url).query)['dl_target_url'].pop()

            if '//s.aliexpress.com' in supplier_url.lower():
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

        elif get_domain(supplier_url) == 'dropified':
            try:
                user_supplement_id = int(urlparse(supplier_url).path.split('/')[-1])
                user_supplement = UserSupplement.objects.get(id=user_supplement_id, user=user.models_user)
            except:
                raven_client.captureException(level='warning')
                return self.api_error('Product supplier is not correct', status=422)

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

        if user_supplement:
            product.user_supplement = user_supplement

        permissions.user_can_add(user, product)
        product.save()

        supplier = CommerceHQSupplier.objects.create(
            store=product.store,
            product=product,
            product_url=supplier_url,
            supplier_name=data.get('vendor_name', 'Supplier'),
            supplier_url=remove_link_query(data.get('vendor_url', 'http://www.aliexpress.com/')),
            is_default=True
        )

        if user_supplement:
            supplier.supplier_name = SUPPLEMENTS_SUPPLIER
            supplier.notes = user_supplement.title
            supplier.save()

        product.set_default_supplier(supplier, commit=True)
        product.sync()

        return self.api_success({'product': product.id})
