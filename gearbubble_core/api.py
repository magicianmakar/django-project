import json
from urllib.parse import parse_qs, urlparse

import requests

from lib.exceptions import capture_exception, capture_message

from django.utils.decorators import method_decorator
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.core.cache import cache
from django.db import transaction
from django.contrib import messages

from shopified_core import permissions
from shopified_core.api_base import ApiBase
from shopified_core.exceptions import ProductExportException
from shopified_core.decorators import HasSubuserPermission, restrict_subuser_access
from shopified_core.utils import (
    safe_int,
    remove_link_query,
    get_domain,
    clean_tracking_number,
)

from .api_helper import GearBubbleApiHelper
from .models import (
    GearBubbleStore,
    GearBubbleProduct,
    GearBubbleSupplier,
    GearBubbleBoard,
    GearBubbleOrderTrack,
)

from . import utils
from . import tasks


class GearBubbleApi(ApiBase):
    store_label = 'GearBubble'
    store_slug = 'gear'
    board_model = GearBubbleBoard
    product_model = GearBubbleProduct
    order_track_model = GearBubbleOrderTrack
    store_model = GearBubbleStore
    helper = GearBubbleApiHelper()

    def validate_store_data(self, data):
        title = data.get('title', '')
        api_token = data.get('api_token', '')
        mode = data.get('mode')

        error_messages = []

        if len(title) > GearBubbleStore._meta.get_field('title').max_length:
            error_messages.append('Title is too long.')
        if len(api_token) > GearBubbleStore._meta.get_field('api_token').max_length:
            error_messages.append('Consumer secret is too long')

        mode_choices = [choice for choice, readable in GearBubbleStore.MODE_CHOICES]
        if mode and mode not in mode_choices:
            error_messages.append('Mode option not valid')

        return error_messages

    def post_store_add(self, request, user, data):
        if user.is_subuser:
            return self.api_error('Sub-Users can not add new stores.', status=401)

        can_add, total_allowed, user_count = permissions.can_add_store(user)

        if not can_add:
            if user.profile.plan.is_free and user.can_trial():
                from shopify_oauth.views import subscribe_user_to_default_plan

                subscribe_user_to_default_plan(user)
            else:
                capture_message(
                    'Add Extra GearBubble Store',
                    level='warning',
                    extra={
                        'user': user.email,
                        'plan': user.profile.plan.title,
                        'stores': user.profile.get_gear_stores().count()
                    }
                )

                if user.profile.plan.is_free or user.can_trial():
                    url = request.build_absolute_uri('/user/profile#plan')
                    msg = 'Please Activate your account first by visiting:\n{}'.format(url)
                    return self.api_error(msg, status=401)
                else:
                    return self.api_error(
                        'Your plan does not support connecting another GearBubble store. '
                        'Please contact support@shopifiedapp.com to learn how to connect '
                        'more stores.'
                    )

        error_messages = self.validate_store_data(data)
        if len(error_messages) > 0:
            return self.api_error(' '.join(error_messages), status=400)

        store = GearBubbleStore()
        store.user = user.models_user
        store.title = data.get('title', '').strip()
        store.api_token = data.get('api_token', '').strip()
        store.mode = data['mode'] if data.get('mode') else store.mode

        permissions.user_can_add(user, store)
        store.save()

        return self.api_success()

    @method_decorator(restrict_subuser_access)
    def post_store_update(self, request, user, data):
        pk = safe_int(data.get('id'))

        if not pk:
            return self.api_error('Store ID is required.', status=400)

        store = GearBubbleStore.objects.filter(pk=pk).first()

        if not store:
            return self.api_error('Store not found', status=404)

        permissions.user_can_edit(user, store)

        error_messages = self.validate_store_data(data)
        if len(error_messages) > 0:
            return self.api_error(' '.join(error_messages), status=400)

        store.title = data.get('title', '').strip()
        store.api_token = data.get('api_token', '').strip()
        store.mode = data['mode'] if data.get('mode') and user.is_superuser else store.mode
        store.save()

        return self.api_success()

    def get_store(self, request, user, data):
        pk = safe_int(data.get('id'))

        if not pk:
            return self.api_error('Store ID is required.', status=400)

        store = GearBubbleStore.objects.filter(pk=pk, user=user.models_user).first()

        if not store:
            return self.api_error('Store not found', status=404)

        permissions.user_can_view(user, store)

        data = {
            'id': store.id,
            'title': store.title,
            'api_token': store.api_token,
            'mode': store.mode,
        }

        return self.api_success(data)

    @method_decorator(restrict_subuser_access)
    def delete_store(self, request, user, data):
        pk = safe_int(data.get('id'))

        if not pk:
            return self.api_error('Store ID is required.', status=400)

        store = GearBubbleStore.objects.filter(pk=pk).first()

        if not store:
            return self.api_error('Store not found', status=404)

        permissions.user_can_delete(user, store)
        store.is_active = False
        store.save()

        return self.api_success()

    def post_product_export(self, request, user, data):
        store_id = safe_int(data.get('store'))

        try:
            store = GearBubbleStore.objects.get(pk=store_id)
        except GearBubbleStore.DoesNotExist:
            return self.api_error('Store does not exist')

        permissions.user_can_view(user, store)

        if not user.can('send_to_gear.sub', store):
            raise PermissionDenied()

        product_id = safe_int(data.get('product'))

        try:
            product = GearBubbleProduct.objects.get(pk=product_id)
        except GearBubbleProduct.DoesNotExist:
            return self.api_error('Product does not exist')

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
            messages.info(request, 'Processing image(s). Refresh the page later to see image(s) (if any).')
            return self.api_success({'pusher': pusher})

    def post_product_update(self, request, user, data):
        try:
            pk = safe_int(data.get('product', 0))
            product = GearBubbleProduct.objects.get(pk=pk)
            permissions.user_can_edit(user, product)
            product.sync()
            product_data = json.loads(data['data'])
            args = product.id, product_data
            tasks.product_update.apply_async(args=args, countdown=0, expires=60)
            effect_on_current_images = utils.get_effect_on_current_images(product, product_data)

            if effect_on_current_images == 'change':
                messages.info(request, 'Updating image(s). Refresh the page later to see the changes.')

            if effect_on_current_images == 'add':
                messages.info(request, 'Adding image(s). Refresh the page later to see new image(s).')

            return self.api_success()

        except ProductExportException as e:
            return self.api_error(str(e))

    def delete_product(self, request, user, data):
        pk = safe_int(data.get('product'))

        if not pk:
            return self.api_error('Product ID is required.', status=400)

        try:
            product = GearBubbleProduct.objects.get(pk=pk)
        except GearBubbleProduct.DoesNotExist:
            return self.api_error('Product does not exist', status=404)

        permissions.user_can_delete(user, product)

        if not user.can('delete_products.sub', product.store):
            raise PermissionDenied()

        product.delete()

        return self.api_success()

    def post_supplier(self, request, user, data):
        product_id = safe_int(data.get('product'))
        product = GearBubbleProduct.objects.get(id=product_id)
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
            return self.api_error('GearBubbleStore store not found', status=500)

        try:
            product_supplier = GearBubbleSupplier.objects.get(id=data.get('export'), store__in=user.profile.get_gear_stores())

            product_supplier.product = product
            product_supplier.product_url = original_link
            product_supplier.supplier_name = data.get('supplier-name')
            product_supplier.supplier_url = supplier_url
            product_supplier.save()

        except (ValueError, GearBubbleSupplier.DoesNotExist):
            product_supplier = GearBubbleSupplier.objects.create(
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

    def delete_supplier(self, request, user, data):
        product = GearBubbleProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        try:
            supplier = GearBubbleSupplier.objects.get(id=data.get('supplier'), product=product)
        except GearBubbleSupplier.DoesNotExist:
            return self.api_error('Supplier not found.\nPlease reload the page and try again.')

        need_update = product.default_supplier == supplier

        supplier.delete()

        if need_update:
            other_supplier = product.get_suppliers().first()
            if other_supplier:
                product.set_default_supplier(other_supplier)
                product.save()

        return self.api_success()

    def post_supplier_default(self, request, user, data):
        product = GearBubbleProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        try:
            supplier = GearBubbleSupplier.objects.get(id=data.get('export'), product=product)
        except GearBubbleSupplier.DoesNotExist:
            return self.api_error('Supplier not found.\nPlease reload the page and try again.')

        product.set_default_supplier(supplier, commit=True)

        return self.api_success()

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def delete_board(self, request, user, data):
        board_id = safe_int(data.get('board_id'))

        try:
            board = GearBubbleBoard.objects.get(pk=board_id)
        except GearBubbleBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)

        permissions.user_can_delete(user, board)
        board.delete()

        return self.api_success()

    def post_order_fulfill(self, request, user, data):
        try:
            store = GearBubbleStore.objects.get(id=safe_int(data.get('store')))
        except GearBubbleStore.DoesNotExist:
            capture_exception()
            return self.api_error('Store {} not found'.format(data.get('store')), status=404)

        if not user.can('place_orders.sub', store):
            raise PermissionDenied()

        permissions.user_can_view(user, store)

        order_id = safe_int(data.get('order_id'))
        line_id = safe_int(data.get('line_id'))
        source_id = data.get('aliexpress_order_id')

        if not (order_id and line_id):
            return self.api_error('Required input is missing')

        try:
            assert len(source_id) > 0, 'Empty Order ID'
            source_id.encode('ascii')
        except AssertionError as e:
            capture_message('Invalid supplier order ID')
            return self.api_error(str(e), status=501)
        except UnicodeEncodeError:
            return self.api_error('Order ID is invalid', status=501)

        order_updater = utils.GearOrderUpdater(store, order_id)

        tracks = GearBubbleOrderTrack.objects.filter(store=store,
                                                     order_id=order_id,
                                                     line_id=line_id)
        tracks_count = tracks.count()

        if tracks_count > 1:
            tracks.delete()

        if tracks_count == 1:
            saved_track = tracks.first()

            if saved_track.source_id and source_id != saved_track.source_id:
                return self.api_error('This order already has a supplier order ID', status=422)

        seen_source_orders = GearBubbleOrderTrack.objects.filter(store=store, source_id=source_id)
        seen_source_orders = seen_source_orders.values_list('order_id', flat=True)

        if len(seen_source_orders) and int(order_id) not in seen_source_orders and not data.get('forced'):
            return self.api_error('Supplier order ID is linked to another order', status=409)

        track, created = GearBubbleOrderTrack.objects.update_or_create(
            store=store,
            order_id=order_id,
            line_id=line_id,
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
            'source_id': source_id,
            'source_url': track.get_source_url(),
        })

        if not settings.DEBUG and 'oberlo.com' not in request.META.get('HTTP_REFERER', ''):
            order_updater.delay_save()

        return self.api_success({'order_track_id': track.id})

    def delete_order_fulfill(self, request, user, data):
        user = user.models_user
        order_id, line_id = safe_int(data.get('order_id')), safe_int(data.get('line_id'))
        orders = GearBubbleOrderTrack.objects.filter(user=user, order_id=order_id, line_id=line_id)

        if not len(orders) > 0:
            return self.api_error('Order not found.', status=404)

        for order in orders:
            permissions.user_can_delete(user, order)
            order.delete()
            data = {'store_id': order.store.id, 'order_id': order_id, 'line_id': line_id}
            order.store.pusher_trigger('order-source-id-delete', data)

        return self.api_success()

    def post_fulfill_order(self, request, user, data):
        try:
            store = GearBubbleStore.objects.get(id=safe_int(data.get('fulfill-store')))
        except GearBubbleStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        if not user.can('place_orders.sub', store):
            raise PermissionDenied()

        permissions.user_can_view(user, store)
        tracking_number = data.get('fulfill-tracking-number', '')
        provider_id = int(data.get('fulfill-provider', 0))
        order_id = int(data['fulfill-order-id'])
        provider_name = utils.get_shipping_carrier_name(store, provider_id)

        if provider_name == 'Custom Provider':
            provider_name = data.get('fulfill-provider-name', provider_name)
        if not provider_name:
            return self.api_error('Invalid shipping provider')

        fulfillment = {'tracking_number': tracking_number, 'tracking_company': provider_name}
        api_url = store.get_api_url('orders/{}/private_fulfillments'.format(order_id))

        r = None
        try:
            r = store.request.post(api_url, json={'fulfillment': fulfillment})
            r.raise_for_status()
        except Exception:
            capture_exception(level='warning', extra={'response': r.text if r else ''})
            return self.api_error('GearBubble API Error')

        return self.api_success()

    def post_order_fulfill_update(self, request, user, data):
        if data.get('store'):
            try:
                store = GearBubbleStore.objects.get(pk=safe_int(data.get('store')))
            except GearBubbleStore.DoesNotExist:
                return self.api_error('Store Not Found', status=404)

            if not user.can('place_orders.sub', store):
                raise PermissionDenied()

        try:
            order = GearBubbleOrderTrack.objects.get(id=data.get('order'))
        except GearBubbleOrderTrack.DoesNotExist:
            return self.api_error('Order Not Found', status=404)

        permissions.user_can_edit(user, order)
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

        return self.api_success()

    def get_user_statistics(self, request, user, data):
        stores = cache.get('gear_user_statistics_{}'.format(user.id))

        if not stores and not data.get('cache_only'):
            if user.models_user.profile.get_gear_stores().count() < 10:
                task = tasks.calculate_user_statistics.apply_async(args=[user.id], expires=60)
                return self.api_success({'task': task.id})

        return self.api_success({'stores': stores})

    def post_gearbubble_products(self, request, user, data):
        store = safe_int(data.get('store'))

        if not store:
            return self.api_error('No store was selected', status=404)

        try:
            store = GearBubbleStore.objects.get(id=store)
            permissions.user_can_view(user, store)
            page = safe_int(data.get('page'), 1)
            params = {'limit': 25, 'page': page, 'fields': 'id,images,title'}

            if data.get('query'):
                # Note: It takes 2 to 3 hours for a newly added product to be searchable
                params['search'] = data['query']

            r = store.request.get(store.get_api_url('private_products'), params=params)

            if r.ok:
                gearbubble_products = r.json()['products']
            elif r.status_code == 404:
                gearbubble_products = []
            else:
                return self.api_error('GearBubble API Error', status=500)

            products = []

            for product in gearbubble_products:
                product['image'] = next(iter(product['images']), {})
                products.append(product)

            return self.api_success({'products': products, 'page': page, 'next': page + 1})

        except GearBubbleStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

    def post_variant_image(self, request, user, data):
        store_id = safe_int(data.get('store'))
        product_id = safe_int(data.get('product'))
        variant_id = safe_int(data.get('variant'))
        image_src = data.get('image_src')

        try:
            store = GearBubbleStore.objects.get(id=store_id)
        except GearBubbleStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        permissions.user_can_view(user, store)

        try:
            product = GearBubbleProduct.objects.get(store=store, source_id=product_id)
        except GearBubbleProduct.DoesNotExist:
            return self.api_error('Product not found', status=404)

        permissions.user_can_edit(user, product)

        path = store.get_api_url('private_products/{}'.format(product_id))
        data = {'id': product_id, 'variants': [{'id': variant_id, 'image': image_src}]}
        r = store.request.put(path, json={'product': data})
        r.raise_for_status()

        return self.api_success()

    def post_import_product(self, request, user, data):
        store_id = safe_int(data.get('store'))

        try:
            store = GearBubbleStore.objects.get(id=store_id)
        except GearBubbleStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        permissions.user_can_view(user, store)
        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)

        if not can_add:
            return self.api_error(
                'Your current plan allow up to %d saved products, currently you have %d saved products.'
                % (total_allowed, user_count), status=401)

        source_id = safe_int(data.get('product'))
        supplier_url = data.get('supplier')

        if source_id:
            if user.models_user.gearbubbleproduct_set.filter(source_id=source_id).count():
                return self.api_error('Product is already import/connected', status=422)
        else:
            return self.api_error('GearBubble Product ID is missing', status=422)

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

        product = GearBubbleProduct(
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

            supplier = GearBubbleSupplier.objects.create(
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
