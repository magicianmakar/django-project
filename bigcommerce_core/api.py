import json
from functools import cmp_to_key
from urllib.parse import parse_qs, urlparse

import requests

from requests.exceptions import HTTPError
from lib.exceptions import capture_exception, capture_message

from django.core.validators import URLValidator
from django.core.exceptions import ValidationError, PermissionDenied
from django.conf import settings
from django.utils import timezone
from django.db import transaction

from shopified_core import permissions
from shopified_core.api_base import ApiBase
from shopified_core.exceptions import ProductExportException
from shopified_core.utils import (
    safe_int,
    get_domain,
    remove_link_query,
    clean_tracking_number,
    CancelledOrderAlert
)
from product_alerts.utils import unmonitor_store
from supplements.models import UserSupplement

from .api_helper import BigCommerceApiHelper
from .models import (
    BigCommerceStore,
    BigCommerceProduct,
    BigCommerceSupplier,
    BigCommerceBoard,
    BigCommerceOrderTrack
)
from . import tasks
from . import utils


class BigCommerceStoreApi(ApiBase):
    store_label = 'BigCommerce'
    store_slug = 'bigcommerce'
    board_model = BigCommerceBoard
    product_model = BigCommerceProduct
    order_track_model = BigCommerceOrderTrack
    store_model = BigCommerceStore
    helper = BigCommerceApiHelper()

    def delete_store(self, request, user, data):
        if user.is_subuser:
            raise PermissionDenied()

        pk = int(data.get('id', 0))
        if not pk:
            return self.api_error('Store ID is required.', status=400)

        try:
            store = BigCommerceStore.objects.get(user=user, pk=pk)
        except BigCommerceStore.DoesNotExist:
            return self.api_error('Store not found.', status=404)

        permissions.user_can_delete(user, store)
        store.is_active = False
        store.uninstalled_at = timezone.now()
        store.save()

        unmonitor_store(store)

        return self.api_success()

    def get_store(self, request, user, data):
        pk = int(data.get('id', 0))
        if not pk:
            return self.api_error('Store ID is required.', status=400)

        try:
            store = BigCommerceStore.objects.get(pk=pk, user=user.models_user)
        except BigCommerceStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        permissions.user_can_view(user, store)

        return self.api_success({
            'id': store.id,
            'title': store.title,
            'api_url': store.api_url,
            # 'api_key': store.api_key,
            # 'api_token': store.api_token,
        })

    def get_store_verify(self, request, user, data):
        try:
            store = BigCommerceStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except BigCommerceStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        try:
            r = store.request.get(url=store.get_api_url('v2/store'))
            r.raise_for_status()

            return self.api_success({'store': store.get_store_url()})

        except:
            return self.api_error('API credentials are not correct')

    def post_bigcommerce_products(self, request, user, data):
        store = safe_int(data.get('store'))
        if not store:
            return self.api_error('No store was selected', status=404)
        try:
            store = BigCommerceStore.objects.get(id=store)
            permissions.user_can_view(user, store)
            page = safe_int(data.get('page'), 1)
            limit = 100
            params = {'limit': limit, 'page': page}

            if data.get('query'):
                params['name'] = data['query']
            params['include'] = 'variants,images'

            try:
                r = store.request.get(url=store.get_api_url('v3/catalog/products'), params=params)
                r.raise_for_status()
            except HTTPError:
                return self.api_error('BigCommerce API Error', status=500)

            products = []
            for product in r.json()['data']:
                if product.get('images'):
                    product['image'] = {'src': product['images'][0]['url_standard']}
                products.append(product)

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
                'next': page + 1 if len(products) == limit else None})

        except BigCommerceStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

    def post_import_product(self, request, user, data):
        try:
            store = BigCommerceStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)
        except BigCommerceStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)
        if not can_add:
            return self.api_error(
                'Your current plan allow up to %d saved products, currently you have %d saved products.'
                % (total_allowed, user_count), status=401)

        source_id = safe_int(data.get('product'))
        supplier_url = data.get('supplier')

        if source_id:
            if user.models_user.bigcommerceproduct_set.filter(store=store, source_id=source_id).count():
                return self.api_error('Product is already import/connected', status=422)
        else:
            return self.api_error('BigCommerce Product ID is missing', status=422)

        if not supplier_url:
            return self.api_error('Supplier URL is missing', status=422)

        if get_domain(supplier_url) == 'aliexpress':
            if '/deep_link.htm' in supplier_url.lower():
                supplier_url = parse_qs(urlparse(supplier_url).query)['dl_target_url'].pop()

            if 's.aliexpress.com' in supplier_url.lower():
                rep = requests.get(supplier_url, allow_redirects=False)
                rep.raise_for_status()

                supplier_url = rep.headers.get('location')

                if '/deep_link.htm' in supplier_url:
                    capture_message(
                        'Deep link in redirection',
                        level='warning',
                        extra={
                            'location': supplier_url,
                            'supplier_url': data.get('supplier')
                        })

            supplier_url = remove_link_query(supplier_url)

        user_supplement = None

        if get_domain(supplier_url) == 'dropified':
            try:
                user_supplement_id = int(urlparse(supplier_url).path.split('/')[-1])
                user_supplement = UserSupplement.objects.get(id=user_supplement_id, user=user.models_user)
            except:
                return self.api_error('Product supplier is not correct', status=422)

        product = BigCommerceProduct(
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

        if user_supplement:
            product.user_supplement = user_supplement

        permissions.user_can_add(user, product)

        with transaction.atomic():
            product.save()

            supplier = BigCommerceSupplier.objects.create(
                store=product.store,
                product=product,
                product_url=supplier_url,
                supplier_name=data.get('vendor_name', 'Supplier'),
                supplier_url=remove_link_query(data.get('vendor_url', 'http://www.aliexpress.com/')),
                is_default=True
            )

            product.set_default_supplier(supplier, commit=True)
            product.sync()

        return self.api_success({'product': product.id})

    def get_product_bigcommerce_id(self, request, user, data):
        product = data.get('product').split(',')
        product_ids = [int(id) for id in product]
        ids = BigCommerceProduct.objects.filter(user=user.models_user, pk__in=product_ids) \
                                .distinct() \
                                .values_list('source_id', flat=True)

        return self.api_success({'ids': list(ids)})

    def delete_product(self, request, user, data):
        try:
            pk = safe_int(data.get('product'))
            product = BigCommerceProduct.objects.get(pk=pk)
            permissions.user_can_delete(user, product)

        except BigCommerceProduct.DoesNotExist:
            return self.api_error('Product does not exists', status=404)

        if not user.can('delete_products.sub', product.store):
            raise PermissionDenied()

        product.delete()

        return self.api_success()

    def post_product_export(self, request, user, data):
        try:
            store = BigCommerceStore.objects.get(pk=safe_int(data.get('store')))
        except BigCommerceStore.DoesNotExist:
            return self.api_error('Store does not exist')
        else:
            permissions.user_can_view(user, store)
            if not user.can('send_to_bigcommerce.sub', store):
                raise PermissionDenied()

        try:
            product = BigCommerceProduct.objects.get(pk=safe_int(data.get('product')))
        except BigCommerceProduct.DoesNotExist:
            return self.api_error('Product does not exist')
        else:
            permissions.user_can_view(user, product)

        try:
            publish = data.get('publish')
            publish = publish if publish is None else publish == 'true'
            args = [store.id, product.id, user.id, publish]
            tasks.product_export.apply_async(args=args, countdown=0, expires=120)
        except ProductExportException as e:
            return self.api_error(str(e))
        else:
            pusher = {'key': settings.PUSHER_KEY, 'channel': store.pusher_channel()}
            return self.api_success({'pusher': pusher})

    def post_product_update(self, request, user, data):
        try:
            pk = safe_int(data.get('product', 0))
            product = BigCommerceProduct.objects.get(pk=pk)
            permissions.user_can_edit(user, product)
            product_data = json.loads(data['data'])
            args = product.id, product_data
            tasks.product_update.apply_async(args=args, countdown=0, expires=60)

            return self.api_success()

        except ProductExportException as e:
            return self.api_error(str(e))

    def post_supplier(self, request, user, data):
        product = BigCommerceProduct.objects.get(id=data.get('product'))
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
            return self.api_error('BigCommerceCommerce store not found', status=500)

        try:
            product_supplier = BigCommerceSupplier.objects.get(id=data.get('export'), store__in=user.profile.get_bigcommerce_stores())

            product_supplier.product = product
            product_supplier.product_url = original_link
            product_supplier.supplier_name = data.get('supplier-name')
            product_supplier.supplier_url = supplier_url
            product_supplier.save()

        except (ValueError, BigCommerceSupplier.DoesNotExist):
            product_supplier = BigCommerceSupplier.objects.create(
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

    def post_bundles_mapping(self, request, user, data):
        product = BigCommerceProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        product.set_bundle_mapping(data.get('mapping'))
        product.save()

        return self.api_success()

    def post_supplier_default(self, request, user, data):
        product = BigCommerceProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        try:
            supplier = BigCommerceSupplier.objects.get(id=data.get('export'), product=product)
        except BigCommerceSupplier.DoesNotExist:
            return self.api_error('Supplier not found.\nPlease reload the page and try again.')

        product.set_default_supplier(supplier, commit=True)

        return self.api_success()

    def post_variant_image(self, request, user, data):
        store_id = safe_int(data.get('store'))
        product_id = safe_int(data.get('product'))
        variant_id = safe_int(data.get('variant'))
        image_id = safe_int(data.get('image'))

        try:
            store = BigCommerceStore.objects.get(id=store_id)
            permissions.user_can_view(user, store)
        except BigCommerceStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        try:
            product = BigCommerceProduct.objects.get(store=store, source_id=product_id)
            permissions.user_can_edit(user, product)
        except BigCommerceProduct.DoesNotExist:
            return self.api_error('Product not found', status=404)

        data = {'image_url': image_id}
        r = store.request.post(
            url=store.get_api_url('v3/catalog/products/{}/variants/{}/image'.format(product_id, variant_id)),
            json=data
        )
        r.raise_for_status()

        return self.api_success()

    def post_fulfill_order(self, request, user, data):
        try:
            store = BigCommerceStore.objects.get(id=data.get('fulfill-store'))
        except BigCommerceStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        if not user.can('place_orders.sub', store):
            raise PermissionDenied()

        permissions.user_can_view(user, store)
        tracking_number = data.get('fulfill-tracking-number', '')
        provider_id = data.get('fulfill-provider', 'custom')
        tracking_link = data.get('fulfill-tracking-link', '')
        order_id = int(data['fulfill-order-id'])
        line_id = int(data['fulfill-line-id'])
        # product_id = int(data['fulfill-product-id'])
        # date_shipped = data.get('fulfill-date-shipped')

        provider_name = ''
        if provider_id == 'custom':
            provider_id = ''
            provider_name = data.get('fulfill-provider-name', '')

        if tracking_link:
            try:
                validate = URLValidator()
                validate(tracking_link)
            except ValidationError as e:
                return self.api_error(','.join(e))

        product_data = utils.get_order_product_data(store, {'id': order_id})

        for line_item in product_data:
            if line_item['id'] == line_id:
                target_line_item = line_item

        r = None
        try:
            data = {
                'tracking_number': tracking_number,
                'order_address_id': target_line_item['order_address_id'],
                'shipping_provider': provider_id,
                'shipping_method': provider_name,
                'items': [
                    {
                        'order_product_id': target_line_item['id'],
                        'quantity': target_line_item['quantity']
                    }
                ],
                'comments': tracking_link,
                # 'date_created': date_shipped,
            }
            r = store.request.post(
                url=store.get_api_url('v2/orders/{}/shipments'.format(order_id)),
                json=data
            )
            r.raise_for_status()
            target_line_item['quantity_shipped'] = target_line_item['quantity']
        except:
            capture_exception(level='warning', extra={'response': r.text if r else ''})
            return self.api_error('BigCommerce API Error')

        if len(utils.get_unfulfilled_items(product_data)) == 0:
            utils.update_order_status(store, order_id, 10)

        return self.api_success()

    def post_order_fulfill(self, request, user, data):
        try:
            store = BigCommerceStore.objects.get(id=int(data.get('store')))
        except BigCommerceStore.DoesNotExist:
            capture_exception()
            return self.api_error('Store {} not found'.format(data.get('store')), status=404)

        if not user.can('place_orders.sub', store):
            raise PermissionDenied()

        permissions.user_can_view(user, store)

        order_id = safe_int(data.get('order_id'))
        line_id = safe_int(data.get('line_id'))

        if not (order_id and line_id):
            return self.api_error('Required input is missing')

        product_id = utils.get_order_track_product_id(store, order_id, line_id)
        source_id = data.get('aliexpress_order_id')

        try:
            assert len(source_id) > 0, 'Empty Order ID'
            source_id.encode('ascii')
        except AssertionError as e:
            capture_message('Invalid supplier order ID')
            return self.api_error(str(e), status=501)
        except UnicodeEncodeError:
            return self.api_error('Order ID is invalid', status=501)

        order_updater = utils.BigCommerceOrderUpdater(store, order_id)

        tracks = BigCommerceOrderTrack.objects.filter(store=store,
                                                      order_id=order_id,
                                                      line_id=line_id,
                                                      product_id=product_id)
        tracks_count = tracks.count()

        if tracks_count > 1:
            tracks.delete()

        if tracks_count == 1:
            saved_track = tracks.first()

            if saved_track.source_id and source_id != saved_track.source_id:
                return self.api_error('This order already has a supplier order ID', status=422)

        seen_source_orders = BigCommerceOrderTrack.objects.filter(store=store, source_id=source_id)
        seen_source_orders = seen_source_orders.values_list('order_id', flat=True)

        if len(seen_source_orders) and int(order_id) not in seen_source_orders and not data.get('forced'):
            return self.api_error('Supplier order ID is linked to another order', status=409)

        track, created = BigCommerceOrderTrack.objects.update_or_create(
            store=store,
            order_id=order_id,
            line_id=line_id,
            product_id=product_id,
            defaults={
                'user': user.models_user,
                'source_id': source_id,
                'source_type': data.get('source_type'),
                'created_at': timezone.now(),
                'updated_at': timezone.now(),
                'status_updated_at': timezone.now()})

        if user.profile.get_config_value('aliexpress_as_notes', True):
            order_updater.mark_as_ordered_note(line_id, source_id, track)

        store.pusher_trigger('order-source-id-add', {
            'track': track.id,
            'order_id': order_id,
            'line_id': line_id,
            'product_id': product_id,
            'source_id': source_id,
            'source_url': track.get_source_url(),
        })

        utils.update_order_status(store, order_id, 'processing')

        if not settings.DEBUG and 'oberlo.com' not in request.META.get('HTTP_REFERER', ''):
            order_updater.delay_save()

        return self.api_success({'order_track_id': track.id})

    def post_order_fulfill_update(self, request, user, data):
        if data.get('store'):
            store = BigCommerceStore.objects.get(pk=safe_int(data['store']))
            if not user.can('place_orders.sub', store):
                raise PermissionDenied()

        try:
            order = BigCommerceOrderTrack.objects.get(id=data.get('order'))
            permissions.user_can_edit(user, order)
        except BigCommerceOrderTrack.DoesNotExist:
            return self.api_error('Order Not Found', status=404)

        cancelled_order_alert = CancelledOrderAlert(user.models_user,
                                                    data.get('source_id'),
                                                    data.get('end_reason'),
                                                    order.source_status_details,
                                                    order)

        order.source_status = data.get('status')
        order.source_tracking = clean_tracking_number(data.get('tracking_number'))
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

        # Send e-mail notifications for cancelled orders
        cancelled_order_alert.send_email()

        return self.api_success()

    def delete_order_fulfill(self, request, user, data):
        order_id, line_id = safe_int(data.get('order_id')), safe_int(data.get('line_id'))
        orders = BigCommerceOrderTrack.objects.filter(user=user.models_user,
                                                      order_id=order_id,
                                                      line_id=line_id)
        if not len(orders) > 0:
            return self.api_error('Order not found.', status=404)

        for order in orders:
            permissions.user_can_delete(user, order)
            order.delete()
            data = {
                'store_id': order.store.id,
                'order_id': order.order_id,
                'line_id': order.line_id,
                'product_id': order.product_id}

            order.store.pusher_trigger('order-source-id-delete', data)

        return self.api_success()

    def delete_board(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        try:
            pk = safe_int(data.get('board_id'))
            board = BigCommerceBoard.objects.get(pk=pk)
        except BigCommerceBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)
        else:
            permissions.user_can_delete(user, board)
            board.delete()
            return self.api_success()

    def delete_supplier(self, request, user, data):
        product = BigCommerceProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        try:
            supplier = BigCommerceSupplier.objects.get(id=data.get('supplier'), product=product)
        except BigCommerceSupplier.DoesNotExist:
            return self.api_error('Supplier not found.\nPlease reload the page and try again.')

        need_update = product.default_supplier == supplier

        supplier.delete()

        if need_update:
            other_supplier = product.get_suppliers().first()
            if other_supplier:
                product.set_default_supplier(other_supplier)
                product.save()

        return self.api_success()

    def get_order_notes(self, request, user, data):
        store = BigCommerceStore.objects.get(id=data['store'])
        permissions.user_can_view(user, store)
        order_ids = data.get('order_ids').split(',')

        tasks.get_latest_order_note_task.apply_async(args=[store.id, order_ids], expires=120)

        return self.api_success()
