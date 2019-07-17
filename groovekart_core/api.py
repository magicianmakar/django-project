import json
import re
import requests
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.validators import URLValidator
from django.db import transaction
from django.template.defaultfilters import truncatewords
from django.utils import timezone
from django.utils.decorators import method_decorator
from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core import permissions
from shopified_core.api_base import ApiBase
from shopified_core.decorators import HasSubuserPermission, restrict_subuser_access
from shopified_core.exceptions import ProductExportException
from shopified_core.utils import (
    safe_int,
    remove_link_query,
    get_domain,
)

from .api_helper import GrooveKartApiHelper
from .models import (
    GrooveKartStore,
    GrooveKartProduct,
    GrooveKartSupplier,
    GrooveKartBoard,
    GrooveKartUserUpload,
    GrooveKartOrderTrack,
)
from . import tasks
from . import utils


class GrooveKartApi(ApiBase):
    store_label = 'GrooveKart'
    store_slug = 'gkart'
    board_model = GrooveKartBoard
    product_model = GrooveKartProduct
    order_track_model = GrooveKartOrderTrack
    store_model = GrooveKartStore
    helper = GrooveKartApiHelper()
    order_updater = utils.GrooveKartOrderUpdater

    def validate_store_data(self, data):
        title = data.get('title', '')
        api_url = data.get('api_url', '')
        api_token = data.get('api_token', '')
        api_key = data.get('api_key')

        error_messages = []

        if not(api_url):
            error_messages.append('The store URL is required.')
        if len(title) > GrooveKartStore._meta.get_field('title').max_length:
            error_messages.append('Title is too long.')
        if len(api_token) > GrooveKartStore._meta.get_field('api_token').max_length:
            error_messages.append('Auth token is too long')
        if len(api_key) > GrooveKartStore._meta.get_field('api_key').max_length:
            error_messages.append('API key is too long')

        try:
            validate = URLValidator()
            validate(api_url)
        except ValidationError:
            error_messages.append('The URL is invalid.')

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
                raven_client.captureMessage(
                    'Add Extra GrooveKart Store',
                    level='warning',
                    extra={
                        'user': user.email,
                        'plan': user.profile.plan.title,
                        'stores': user.profile.get_gkart_stores().count()
                    }
                )

                if user.profile.plan.is_free or user.can_trial():
                    url = request.build_absolute_uri('/user/profile#plan')
                    msg = 'Please Activate your account first by visiting:\n{}'.format(url)
                    return self.api_error(msg, status=401)
                else:
                    return self.api_error(
                        'Your plan does not support connecting another GrooveKart store. '
                        'Please contact support@dropified.com to learn how to connect '
                        'more stores.'
                    )

        error_messages = self.validate_store_data(data)
        if len(error_messages) > 0:
            return self.api_error(' '.join(error_messages), status=400)

        store = GrooveKartStore()
        store.user = user.models_user
        store.title = data.get('title', '').strip()
        store.api_url = data.get('api_url', '').strip()
        store.api_token = data.get('api_token', '').strip()
        store.api_key = data.get('api_key', '').strip()

        permissions.user_can_add(user, store)
        store.save()

        return self.api_success()

    @method_decorator(restrict_subuser_access)
    def post_store_update(self, request, user, data):
        pk = safe_int(data.get('id'))

        if not pk:
            return self.api_error('Store ID is required.', status=400)

        store = GrooveKartStore.objects.filter(pk=pk).first()

        if not store:
            return self.api_error('Store not found', status=404)

        permissions.user_can_edit(user, store)

        error_messages = self.validate_store_data(data)
        if len(error_messages) > 0:
            return self.api_error(' '.join(error_messages), status=400)

        store.title = data.get('title', '').strip()
        store.api_url = data.get('api_url', '').strip()
        store.api_token = data.get('api_token', '').strip()
        store.api_key = data.get('api_key', '').strip()
        store.save()

        return self.api_success()

    def get_store_verify(self, request, user, data):
        try:
            store = GrooveKartStore.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except GrooveKartStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        rep = None
        try:
            rep = store.request.post(
                store.get_api_url('list_categories.json'),
                json={}
            )

            rep.raise_for_status()

            return self.api_success({'store': store.get_store_url()})

        except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout):
            return self.api_error('Connection to your store is not successful at:\n{}'.format(store.get_store_url()))

        except IndexError:
            return self.api_error('Your Store link is not correct:\n{}'.format(store.api_url))
        except:
            return self.api_error('API credetnails is not correct\nError: {}'.format(rep.reason if rep is not None else 'Unknown Issue'))

    def get_store(self, request, user, data):
        pk = safe_int(data.get('id'))

        if not pk:
            return self.api_error('Store ID is required.', status=400)

        store = GrooveKartStore.objects.filter(pk=pk, user=user.models_user).first()

        if not store:
            return self.api_error('Store not found', status=404)

        permissions.user_can_view(user, store)

        data = {
            'id': store.id,
            'title': store.title,
            'api_url': store.api_url,
            'api_token': store.api_token,
            'api_key': store.api_key,
        }

        return self.api_success(data)

    @method_decorator(restrict_subuser_access)
    def delete_store(self, request, user, data):
        pk = safe_int(data.get('id'))

        if not pk:
            return self.api_error('Store ID is required.', status=400)

        store = GrooveKartStore.objects.filter(pk=pk).first()

        if not store:
            return self.api_error('Store not found', status=404)

        permissions.user_can_delete(user, store)
        store.is_active = False
        store.save()

        return self.api_success()

    def get_user_statistics(self, request, user, data):
        stores = cache.get('gkart_user_statistics_{}'.format(user.id))

        if not stores and not data.get('cache_only'):
            if user.models_user.profile.get_gkart_stores().count() < 10:
                task = tasks.calculate_user_statistics.apply_async(args=[user.id], expires=60)
                return self.api_success({'task': task.id})

        return self.api_success({'stores': stores})

    def post_groovekart_products(self, request, user, data):
        store = safe_int(data.get('store'))

        if not store:
            return self.api_error('No store was selected', status=404)

        try:
            store = GrooveKartStore.objects.get(id=store)
            permissions.user_can_view(user, store)
            page = safe_int(data.get('page'), 1)
            params = {
                'limit': 10,
                'offset': 10 * (page - 1),
                'order_by': 'date_add'
            }
            url = store.get_api_url('list_products.json')
            if data.get('query'):
                params['keyword'] = data.get('query')
                url = store.get_api_url('search_products.json')

            r = store.request.post(url, json=params)
            if r.ok:
                products = r.json()['products']
            else:
                products = []

            return self.api_success({'products': products, 'page': page, 'next': page + 1})

        except GrooveKartStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

    def delete_product(self, request, user, data):
        pk = safe_int(data.get('product'))

        if not pk:
            return self.api_error('Product ID is required.', status=400)

        try:
            product = GrooveKartProduct.objects.get(pk=pk)
        except GrooveKartProduct.DoesNotExist:
            return self.api_error('Product does not exist', status=404)

        permissions.user_can_delete(user, product)

        if not user.can('delete_products.sub', product.store):
            raise PermissionDenied()

        product.delete()

        return self.api_success()

    def post_product_export(self, request, user, data):
        store_id = safe_int(data.get('store'))

        try:
            store = GrooveKartStore.objects.get(pk=store_id)
        except GrooveKartStore.DoesNotExist:
            return self.api_error('Store does not exist')

        permissions.user_can_view(user, store)

        if not user.can('send_to_gkart.sub', store):
            raise PermissionDenied()

        product_id = safe_int(data.get('product'))

        try:
            product = GrooveKartProduct.objects.get(pk=product_id)
        except GrooveKartProduct.DoesNotExist:
            return self.api_error('Product does not exist')

        permissions.user_can_view(user, product)

        try:
            args = [store.id, product.id, user.id]
            tasks.product_export.apply_async(args=args, countdown=0, expires=120)
        except ProductExportException as e:
            return self.api_error(str(e))
        else:
            pusher = {'key': settings.PUSHER_KEY, 'channel': store.pusher_channel()}
            return self.api_success({'pusher': pusher})

    def post_product_update(self, request, user, data):
        try:
            pk = safe_int(data.get('product', 0))
            product = GrooveKartProduct.objects.get(pk=pk)
            permissions.user_can_edit(user, product)
            product.sync()
            product_data = json.loads(data['data'])
            args = product.id, product_data
            tasks.product_update.apply_async(args=args, countdown=0, expires=60)

            return self.api_success()

        except ProductExportException as e:
            return self.api_error(str(e))

    def post_supplier(self, request, user, data):
        product_id = safe_int(data.get('product'))
        product = GrooveKartProduct.objects.get(id=product_id)
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
            return self.api_error('GrooveKart store not found', status=500)

        try:
            product_supplier = GrooveKartSupplier.objects.get(id=data.get('export'), store__in=user.profile.get_gkart_stores())
            product_supplier.product = product
            product_supplier.product_url = original_link
            product_supplier.supplier_name = data.get('supplier-name')
            product_supplier.supplier_url = supplier_url
            product_supplier.save()
        except (ValueError, GrooveKartSupplier.DoesNotExist):
            product_supplier = GrooveKartSupplier.objects.create(
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
        product = GrooveKartProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        try:
            supplier = GrooveKartSupplier.objects.get(id=data.get('export'), product=product)
        except GrooveKartSupplier.DoesNotExist:
            return self.api_error('Supplier not found.\nPlease reload the page and try again.')

        product.set_default_supplier(supplier, commit=True)

        return self.api_success()

    def delete_supplier(self, request, user, data):
        supplier_id = safe_int(data.get('supplier'))

        try:
            product_supplier = GrooveKartSupplier.objects.get(pk=supplier_id)
        except GrooveKartSupplier.DoesNotExist:
            return self.api_error('Supplier Not Found!', status=404)

        permissions.user_can_delete(user, product_supplier)
        product_supplier.delete()

        return self.api_success()

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def delete_board(self, request, user, data):
        board_id = safe_int(data.get('board_id'))

        try:
            board = GrooveKartBoard.objects.get(pk=board_id)
        except GrooveKartBoard.DoesNotExist:
            return self.api_error('Board not found.', status=404)

        permissions.user_can_delete(user, board)
        board.delete()

        return self.api_success()

    def post_fulfill_order(self, request, user, data):
        try:
            store = GrooveKartStore.objects.get(id=safe_int(data.get('fulfill-store')))
        except GrooveKartStore.DoesNotExist:
            return self.api_error('Store not found', status=404)

        if not user.can('place_orders.sub', store):
            raise PermissionDenied()

        permissions.user_can_view(user, store)
        tracking_number = data.get('fulfill-tracking-number', '')
        provider_id = safe_int(data.get('fulfill-provider', 0))
        tracking_link = data.get('fulfill-tracking-link', '')
        order_id = int(data['fulfill-order-id'])
        provider_name = utils.get_shipping_carrier_name(store, provider_id)
        send_shipping_confirmation = (data.get('fulfill-notify-customer') == 'yes')

        if tracking_link:
            try:
                validate = URLValidator()
                validate(tracking_link)
            except ValidationError as e:
                return self.api_error(','.join(e))

        fulfillment = {
            'order_id': order_id,
            'tracking_number': tracking_number,
            'carrier_name': provider_name,
            'carrier_url': tracking_link,
        }

        if data.get('fulfill-notify-customer'):
            fulfillment['send_email'] = send_shipping_confirmation

        api_url = store.get_api_url('trackings.json')

        try:
            r = store.request.post(api_url, json=fulfillment)
            r.raise_for_status()
        except Exception:
            raven_client.captureException(level='warning', extra={'response': r.text})
            return self.api_error('GrooveKart API Error')

        return self.api_success()

    def post_import_product(self, request, user, data):
        store_id = safe_int(data.get('store'))

        try:
            store = GrooveKartStore.objects.get(id=store_id)
        except GrooveKartStore.DoesNotExist:
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
            if user.models_user.groovekartproduct_set.filter(source_id=source_id).count():
                return self.api_error('Product is already import/connected', status=422)
        else:
            return self.api_error('GrooveKart Product ID is missing', status=422)

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
                    raven_client.captureMessage(
                        'Deep link in redirection',
                        level='warning',
                        extra={
                            'location': supplier_url,
                            'supplier_url': data.get('supplier')
                        })

            supplier_url = remove_link_query(supplier_url)

        product = GrooveKartProduct(
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

            supplier = GrooveKartSupplier.objects.create(
                store=product.store,
                product=product,
                product_url=supplier_url,
                supplier_name=data.get('vendor_name', 'Supplier'),
                supplier_url=data.get('vendor_url', 'http://www.aliexpress.com/'),
                is_default=True
            )

            product.set_default_supplier(supplier, commit=True)
            product.save()

        return self.api_success({'product': product.id})

    def post_order_fulfill(self, request, user, data):
        try:
            store = GrooveKartStore.objects.get(id=safe_int(data.get('store')))
        except GrooveKartStore.DoesNotExist:
            raven_client.captureException()
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
            raven_client.captureMessage('Invalid supplier order ID')
            return self.api_error(str(e), status=501)
        except UnicodeEncodeError:
            return self.api_error('Order ID is invalid', status=501)

        order_updater = utils.GrooveKartOrderUpdater(store, order_id)

        tracks = GrooveKartOrderTrack.objects.filter(store=store,
                                                     order_id=order_id,
                                                     line_id=line_id)
        tracks_count = tracks.count()

        if tracks_count > 1:
            tracks.delete()

        if tracks_count == 1:
            saved_track = tracks.first()

            if saved_track.source_id and source_id != saved_track.source_id:
                return self.api_error('This order already has a supplier order ID', status=422)

        seen_source_orders = GrooveKartOrderTrack.objects.filter(store=store, source_id=source_id)
        seen_source_orders = seen_source_orders.values_list('order_id', flat=True)

        if len(seen_source_orders) and int(order_id) not in seen_source_orders and not data.get('forced'):
            return self.api_error('Supplier order ID is linked to another order', status=409)

        track, created = GrooveKartOrderTrack.objects.update_or_create(
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

        order_updater.delay_save()
        if not settings.DEBUG and 'oberlo.com' not in request.META.get('HTTP_REFERER', ''):
            order_updater.delay_save()

        return self.api_success({'order_track_id': track.id})

    def post_order_fulfill_update(self, request, user, data):
        if data.get('store'):
            try:
                store = GrooveKartStore.objects.get(pk=safe_int(data.get('store')))
            except GrooveKartStore.DoesNotExist:
                return self.api_error('Store Not Found', status=404)

            if not user.can('place_orders.sub', store):
                raise PermissionDenied()

        try:
            order = GrooveKartOrderTrack.objects.get(id=data.get('order'))
        except GrooveKartOrderTrack.DoesNotExist:
            return self.api_error('Order Not Found', status=404)

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
        user = user.models_user
        order_id, line_id = safe_int(data.get('order_id')), safe_int(data.get('line_id'))
        orders = GrooveKartOrderTrack.objects.filter(user=user, order_id=order_id, line_id=line_id)

        if not len(orders) > 0:
            return self.api_error('Order not found.', status=404)

        for order in orders:
            permissions.user_can_delete(user, order)
            order.delete()
            data = {'store_id': order.store.id, 'order_id': order_id, 'line_id': line_id}
            order.store.pusher_trigger('order-source-id-delete', data)

        return self.api_success()

    def post_add_user_upload(self, request, user, data):
        product = GrooveKartProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        upload = GrooveKartUserUpload(user=user.models_user, product=product, url=data.get('url'))
        permissions.user_can_add(user, upload)

        upload.save()

        return self.api_success()

    def get_autocomplete(self, request, user, data):
        q = data.get('query', '').strip()
        if not q:
            q = data.get('term', '').strip()

        if not q:
            return self.api_success({'query': q, 'suggestions': []}, safe=False)

        target = data.get('target')
        if target == 'title':
            results = []
            products = user.models_user.groovekartproduct_set.only('id', 'title', 'data').filter(title__icontains=q, source_id__gt=0)
            store = data.get('store')
            if store:
                products = products.filter(store=store)

            for product in products[:10]:
                results.append({
                    'value': (truncatewords(product.title, 10) if data.get('trunc') else product.title),
                    'data': product.source_id,
                    'image': product.get_image()
                })

            return self.api_success({'query': q, 'suggestions': results}, safe=False)

        elif target == 'types':
            types = []
            for product in request.user.models_user.groovekartproduct_set.only('product_type').filter(product_type__icontains=q)[:10]:
                if product.product_type not in types:
                    types.append(product.product_type)

            return self.api_success({'query': q, 'suggestions': [{'value': i, 'data': i} for i in types]}, safe=False)

        return self.api_error({'error': 'Target not found'}, status=404)
