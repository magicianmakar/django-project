import simplejson as json
import arrow
import itertools

import phonenumbers
from lib.exceptions import capture_exception

from django.contrib.auth.models import User
from django.views.generic import View
from django.utils.decorators import method_decorator
from django.db.models import ObjectDoesNotExist, F
from django.http import JsonResponse
from django.core.cache import cache
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404

from last_seen.models import LastSeen

from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import (
    dict_val,
    safe_int,
    safe_float,
    safe_str,
    order_data_cache,
    order_phone_number,
    orders_update_limit,
    serializers_orders_track,
    using_replica,
)
from shopified_core.models_utils import get_store_model, get_user_upload_model
from shopified_core.shipping_helper import aliexpress_country_code_map, ebay_country_code_map
from shopified_core.decorators import HasSubuserPermission
from product_core.models import ProductBoard

from stripe_subscription.models import ExtraSubUser
from stripe_subscription.signals import get_extra_model_from_store

from product_alerts.models import ProductChange


class ApiBase(ApiResponseMixin, View):
    store_label = None
    store_slug = None
    board_model = None
    product_model = None
    order_track_model = None
    store_model = None
    helper = None

    def __init__(self):
        super(ApiBase, self).__init__()
        self._assert_configured()

    def _assert_configured(self):
        assert self.store_label, 'Store Label is not set'
        assert self.store_slug, 'Store Slug is not set'
        assert self.board_model, 'Boards Model is not set'
        assert self.product_model, 'Product Model is not set'
        assert self.order_track_model, 'Order Track Model is not set'
        assert self.store_model, 'Store Model is not set'
        assert self.helper, 'Helper is not set'

    @property
    def is_shopify(self):
        return self.store_slug == 'shopify'

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def post_boards_add(self, request, user, data):
        can_add, total_allowed, user_count = permissions.can_add_board(user)

        if not can_add:
            return self.api_error(
                'Your current plan allows up to %d board(s). Currently you have %d boards.'
                % (total_allowed, user_count))

        board_name = data.get('title', '').strip()

        if not len(board_name):

            return self.api_error('Board name is required', status=501)

        if self.board_model.objects.filter(user=user, title=board_name).exists():
            return self.api_error('Board name is already exist.', status=501)

        board = self.board_model(title=board_name, user=user.models_user)
        permissions.user_can_add(user, board)

        board.save()

        return self.api_success({
            'board': {
                'id': board.id,
                'title': board.title
            }
        })

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def post_board_favorite(self, request, user, data):
        try:
            board = self.board_model.objects.get(id=data.get('board'))
            permissions.user_can_edit(user, board)

        except ObjectDoesNotExist:
            return self.api_error('Board not found.', status=404)

        board.favorite = bool(data.get('favorite'))
        board.save()

        return self.api_success()

    @method_decorator(HasSubuserPermission('view_product_boards.sub'))
    def get_board_config(self, request, user, data):
        try:
            pk = dict_val(data, ['board', 'board_id'])
            board = self.board_model.objects.get(pk=pk)
            permissions.user_can_edit(user, board)

        except ObjectDoesNotExist:
            return self.api_error('Board not found.', status=404)

        try:
            config = json.loads(board.config)
        except:
            config = {'title': '', 'tags': '', 'type': ''}

        return self.api_success({
            'title': board.title,
            'config': config
        })

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def post_board_config(self, request, user, data):
        try:
            pk = dict_val(data, ['board', 'board_id'])
            board = self.board_model.objects.get(pk=pk)
            permissions.user_can_edit(user, board)

        except ObjectDoesNotExist:
            return self.api_error('Board not found.', status=404)

        board.title = data.get('title')
        board.config = json.dumps({
            'title': data.get('product_title'),
            'tags': data.get('product_tags'),
            'type': data.get('product_type')
        })

        board.save()

        self.helper.smart_board_sync(user.models_user, board)

        return self.api_success()

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def post_board_add_products(self, request, user, data):
        try:
            board = self.board_model.objects.get(id=data.get('board'))
            permissions.user_can_edit(user, board)

        except ObjectDoesNotExist:
            return self.api_error('Board not found.', status=404)

        product_ids = [safe_int(pk) for pk in data.getlist('products[]')]
        products = self.product_model.objects.filter(pk__in=product_ids)

        for product in products:
            permissions.user_can_edit(user, product)

        board.products.add(*products)

        return self.api_success()

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def post_board_empty(self, request, user, data):
        try:
            pk = safe_int(data.get('board_id'))
            board = self.board_model.objects.get(pk=pk)
            permissions.user_can_edit(user, board)
            board.products.clear()
            return self.api_success()
        except ObjectDoesNotExist:
            return self.api_error('Board not found.', status=404)

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def post_product_board(self, request, user, data):
        try:
            product = self.product_model.objects.get(id=data.get('product'))
            permissions.user_can_edit(user, product)
        except ObjectDoesNotExist:
            return self.api_error('Product not found.', status=404)

        if data.get('board') == '0':
            product.boards.clear()
            product.save()
            return self.api_success()
        else:
            try:
                board = self.board_model.objects.get(id=data.get('board'))
                permissions.user_can_edit(user, board)
                board.products.add(product)
                board.save()
                return self.api_success({'board': {'id': board.id, 'title': board.title}})
            except ObjectDoesNotExist:
                return self.api_error('Board not found.', status=404)

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def post_product_board_list(self, request, user, data):
        try:
            product = self.product_model.objects.get(id=data.get('product'))
            permissions.user_can_edit(user, product)
        except ObjectDoesNotExist:
            return self.api_error('Product not found.', status=404)

        if data.get('board') == '0':
            product.boards_list = []
            product.save()
            return self.api_success()
        else:
            try:
                board = ProductBoard.objects.get(id=data.get('board'))
                permissions.user_can_edit(user, board)

                if not product.boards_list:
                    product.boards_list = []

                product.boards_list.append(board.id)
                product.save()

                return self.api_success({'board': {'id': board.id, 'title': board.title}})

            except ObjectDoesNotExist:
                return self.api_error('Board not found.', status=404)

    def get_products_info(self, request, user, data):
        products = {}
        for p in data.getlist('products[]'):
            pk = safe_int(p)
            try:
                product = self.product_model.objects.get(pk=pk)
                permissions.user_can_view(user, product)

                products[p] = json.loads(product.data)
            except:
                return self.api_error('Product not found')

        return JsonResponse(products, safe=False)

    def post_order_fullfill_hide(self, request, user, data):
        try:
            order = self.order_track_model.objects.get(id=data.get('order'))
        except ObjectDoesNotExist:
            return self.api_error('Order track not found', status=404)

        permissions.user_can_edit(user, order)

        order.hidden = data.get('hide') == 'true'
        order.save()

        return self.api_success()

    def post_product_notes(self, request, user, data):
        product = self.product_model.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        product.notes = data.get('notes')
        product.save()

        return self.api_success()

    def post_product_edit(self, request, user, data):
        products = []
        for p in data.getlist('products[]'):
            product = self.product_model.objects.get(id=p)
            permissions.user_can_edit(user, product)

            product_data = json.loads(product.data)

            if 'tags' in data:
                product_data['tags'] = data.get('tags')

            if 'price' in data:
                product_data['price'] = safe_float(data.get('price'))

            if 'compare_at' in data:
                product_data['compare_at_price'] = safe_float(data.get('compare_at'))

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

    def delete_product_connect(self, request, user, data):
        product_ids = data.get('product').split(',')
        for product_id in product_ids:
            product = self.product_model.objects.get(id=product_id)
            permissions.user_can_edit(user, product)

            source_id = product.source_id
            if source_id:
                product.source_id = 0
                product.save()

                self.helper.after_delete_product_connect(product, source_id)

        return self.api_success()

    def get_order_data(self, request, user, data):
        order_key = data.get('order')

        order_key, store = self.helper.format_order_key(order_key)

        try:
            store = self.store_model.objects.get(id=int(store))
        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        permissions.user_can_view(user, store)

        order = order_data_cache(order_key)
        if order:
            if data.get('original') == '1':
                return JsonResponse(order, safe=False)

            if user.models_user.get_config('_static_shipping_address'):
                order['shipping_address'] = user.models_user.get_config('_static_shipping_address')

            if not order['shipping_address'].get('address2'):
                order['shipping_address']['address2'] = ''

            if order.get('supplier_type') == 'ebay':
                order['shipping_address']['country_code'] = ebay_country_code_map(order['shipping_address']['country_code'])
            else:
                order['shipping_address']['country_code'] = aliexpress_country_code_map(order['shipping_address']['country_code'])

            order['ordered'] = False
            order['fast_checkout'] = user.get_config('_fast_order_checkout', True)  # Use Cart for all orders
            order['solve'] = user.models_user.get_config('aliexpress_solve_captcha', True)

            phone = order['order']['phone']
            if type(phone) is dict:
                phone_country, phone_number = order_phone_number(request, user.models_user, phone['number'], phone['country'])
                order['order']['phone'] = phone_number
                order['order']['phoneCountry'] = phone_country

            if not order['order']['phone']:
                order['order']['phone'] = '0000000000'

            if not order['order']['phoneCountry']:
                try:
                    order['order']['phoneCountry'] = f"+{phonenumbers.country_code_for_region(order['shipping_address']['country_code'])}"
                except:
                    capture_exception()

            if order.get('supplier_type') != 'ebay' and safe_str(order['shipping_address']['country_code']).lower() == 'fr':
                if order['order']['phone'] and not order['order']['phone'].startswith('0'):
                    order['order']['phone'] = order['order']['phone'].rjust(10, '0')

            if user.models_user.get_config('_aliexpress_telephone_workarround'):
                order['order']['telephone_workarround'] = True

            try:
                track = self.order_track_model.objects.get(store=store, order_id=order['order_id'], line_id=order['line_id'])

                order['ordered'] = {
                    'time': arrow.get(track.created_at).humanize(),
                    'link': request.build_absolute_uri('/orders/track?hidden=2&query={}'.format(order['order_id']))
                }

            except ObjectDoesNotExist:
                pass
            except:
                capture_exception()

            return JsonResponse(order, safe=False)
        else:
            return self.api_error('Not found: {}'.format(data.get('order')), status=404)

    def get_order_fulfill(self, request, user, data):
        if int(data.get('count', 0)) >= 30:
            raise self.api_error('Not found', status=404)

        if not user.can('orders.use'):
            return self.api_error('Order is not included in your account', status=402)

        try:
            LastSeen.objects.when(user.models_user, 'website')
        except:
            return self.api_error('User is not active', status=429)

        # Get Orders marked as Ordered

        orders = []

        order_ids = data.get('ids')
        all_orders = data.get('all') == 'true' or order_ids
        unfulfilled_only = data.get('unfulfilled_only') != 'false' and not order_ids
        sync_all_orders = cache.get('_sync_all_orders') and data.get('forced') == 'false'
        sync_all_orders_key = f'user_sync_all_orders_{self.store_slug}_{user.id}'

        order_tracks = using_replica(self.order_track_model) \
            .filter(user=user.models_user, hidden=False) \
            .defer('data') \
            .order_by('updated_at')

        created_at_start = None
        created_at_end = None
        created_at_max = arrow.now().replace(days=-60).datetime
        created_at = data.get('created_at')  # Format: %m/%d/%Y-%m/%d/%Y

        if sync_all_orders:
            if cache.get(sync_all_orders_key):
                return self.api_success(orders, safe=False, status=202)
            else:
                cache.set(sync_all_orders_key, True, timeout=7200)

        if created_at:
            created_at_start, created_at_end = created_at.split('-')

            tz = timezone.localtime(timezone.now()).strftime(' %z')
            created_at_start = arrow.get(created_at_start + tz, r'MM/DD/YYYY Z').datetime

            if created_at_end:
                created_at_end = arrow.get(created_at_end + tz, r'MM/DD/YYYY Z')
                created_at_end = created_at_end.span('day')[1].datetime  # Ensure end date is set to last hour in the day

            created_at_max = created_at_start

            if created_at_end:
                order_tracks = order_tracks.filter(created_at__lte=created_at_end)

        if created_at_max and not order_ids:
            order_tracks = order_tracks.filter(created_at__gte=created_at_max)

        if order_ids:
            order_tracks = order_tracks.filter(id__in=order_ids.split(','))

        if unfulfilled_only:
            order_tracks = self.helper.get_unfulfilled_order_tracks(order_tracks)

        if user.is_subuser:
            order_tracks = order_tracks.filter(store__in=self.helper.get_user_stores_for_type(user, flat=True))

        if data.get('store'):
            order_tracks = order_tracks.filter(store=data.get('store'))

        if not data.get('order_id') and not data.get('line_id') and not all_orders and not sync_all_orders:
            limit_key = 'order_fulfill_limit_%d' % user.models_user.id
            limit = cache.get(limit_key)

            if limit is None:
                limit = orders_update_limit(orders_count=order_tracks.count())

                if limit != 20:
                    cache.set(limit_key, limit, timeout=3600)

            if data.get('forced') == 'true':
                limit = limit * 2

            order_tracks = order_tracks[:limit]

        elif data.get('all') == 'true' or sync_all_orders:
            order_tracks = order_tracks.order_by('created_at')

        if data.get('order_id') and data.get('line_id'):
            order_tracks = order_tracks.filter(order_id=data.get('order_id'), line_id=data.get('line_id'))

        if data.get('count_only') == 'true':
            return self.api_success({'pending': order_tracks.count()})

        orders.extend(serializers_orders_track(order_tracks, self.store_slug, humanize=all_orders))

        if not data.get('order_id') and not data.get('line_id'):
            self.order_track_model.objects.filter(user=user.models_user, id__in=[i['id'] for i in orders]) \
                                  .update(check_count=F('check_count') + 1, updated_at=timezone.now())

        return self.api_success(orders, safe=False)

    def get_product_image_download(self, request, user, data):
        try:
            product = self.product_model.objects.get(id=safe_int(data.get('product')))
            permissions.user_can_view(user, product)

        except ObjectDoesNotExist:
            return self.api_error('Product not found', status=404)

        images = product.parsed.get('images')
        if not images:
            return self.api_error('Product doesn\'t have any images', status=422)

        self.helper.create_image_zip(images, product)

        return self.api_success()

    def post_order_note(self, request, user, data):
        try:
            store = self.store_model.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        order_id = data['order_id']
        note = data['note']

        if note is None:
            return self.api_error('Note required')

        if self.helper.set_order_note(store, order_id, note):
            return self.api_success()
        else:
            return self.api_error(f'{self.store_label} API Error', status=422)

    def post_product_connect(self, request, user, data):
        product = self.product_model.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        store = self.store_model.objects.get(id=data.get('store'))
        permissions.user_can_view(user, store)

        # TODO: Change use of data['shopify'] to data['commercehq'] in CommerceHQ
        source_id = safe_int(dict_val(data, ['shopify', 'woocommerce', 'groovekart', 'gearbubble', 'bigcommerce']))

        if source_id != product.source_id or product.store != store:
            connected_to = self.helper.get_connected_products(self.product_model, store, source_id)

            if connected_to.exists():
                error_message = ['The selected product is already connected to:\n']
                pks = connected_to.values_list('pk', flat=True)
                links = []

                for pk in pks:
                    path = self.helper.get_product_path(pk)
                    links.append(request.build_absolute_uri(path))

                error_message = itertools.chain(error_message, links)
                error_message = '\n'.join(error_message)

                return self.api_error(error_message, status=500)

            product.store = store

            if self.is_shopify:
                product.shopify_id = source_id
            else:
                product.source_id = source_id

            product.save()

            self.helper.after_post_product_connect(product, source_id)

        return self.api_success()

    def post_product_duplicate(self, request, user, data):
        product = self.product_model.objects.get(id=data.get('product'))
        permissions.user_can_view(user, product)

        duplicate_product = self.helper.duplicate_product(product)

        return self.api_success({
            'product': {
                'id': duplicate_product.id,
                'url': self.helper.get_product_path(duplicate_product.id)
            }
        })

    def post_product_split_variants(self, request, user, data):
        product = self.product_model.objects.get(id=data.get('product'))
        split_factor = data.get('split_factor')
        permissions.user_can_view(user, product)
        splitted_product_ids = self.helper.split_product(product, split_factor, user)

        return self.api_success({
            'products_ids': splitted_product_ids
        })

    def post_save_for_later(self, request, user, data):
        # DEPRECATE: user pusher-based product save
        # Backward compatibly with Shopify save for later
        return self.post_product_save(request, user, data)

    def post_product_save(self, request, user, data):
        if data.get('store'):
            store = self.store_model.objects.get(pk=data.get('store'))
            if not user.can('save_for_later.sub', store):
                raise PermissionDenied()

        result = self.helper.product_save(data, user.id, self.target, request)
        return self.api_success(result)

    def post_suppliers_mapping(self, request, user, data):
        if not user.can('suppliers_shipping_mapping.use'):
            raise PermissionDenied()

        product = self.product_model.objects.get(id=data.get('product'))
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

                    product.set_variant_mapping(var_mapping, supplier=supplier, update=True, commit=False)

                elif k == 'config':
                    product.set_mapping_config({'supplier': data[k]})

                elif k != 'product':  # Save the variant -> supplier mapping
                    mapping[k] = json.loads(data[k])

            product.set_suppliers_mapping(mapping, commit=False)
            product.set_shipping_mapping(shipping_map, commit=False)

        product.save()

        for i in suppliers_cache.values():
            i.save()

        return self.api_success()

    def post_variants_mapping(self, request, user, data):
        product = self.product_model.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)
        supplier = product.get_suppliers().get(id=data.get('supplier'))
        mapping = {key: value for key, value in list(data.items()) if key not in ['product', 'supplier']}
        supplier = self.helper.set_product_default_supplier(product, supplier)
        product.set_variant_mapping(mapping, supplier=supplier)
        product.save()

        return self.api_success()

    @method_decorator(HasSubuserPermission('edit_product_boards.sub'))
    def delete_board_products(self, request, user, data):
        try:
            pk = safe_int(dict_val(data, ['board', 'board_id']))
            board = self.board_model.objects.get(pk=pk)
            permissions.user_can_edit(user, board)

        except ObjectDoesNotExist:
            return self.api_error('Board not found.', status=404)

        product_ids = [safe_int(pk) for pk in data.getlist('products[]')]
        products = self.product_model.objects.filter(pk__in=product_ids)
        for product in products:
            permissions.user_can_edit(user, product)
            board.products.remove(product)

        return self.api_success()

    def post_alert_archive(self, request, user, data):
        try:
            if data.get('all') == '1':
                store = self.store_model.objects.get(id=data.get('store'))
                permissions.user_can_view(user, store)

                self.helper.filter_productchange_by_store(store).update(hidden=1)

            else:
                alert = ProductChange.objects.get(id=data.get('alert'))
                permissions.user_can_edit(user, alert)

                alert.hidden = 1
                alert.save()

        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        return self.api_success()

    def post_alert_delete(self, request, user, data):
        try:
            store = self.store_model.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

            self.helper.filter_productchange_by_store(store).delete()

        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        return self.api_success()

    def post_product_config(self, request, user, data):
        if not user.can('price_changes.use'):
            raise PermissionDenied()

        product = data.get('product')
        if product:
            product = get_object_or_404(self.product_model, id=product)
            permissions.user_can_edit(request.user, product)
        else:
            return self.api_error('Product not found', status=404)

        try:
            config = json.loads(product.config)
        except:
            config = {}

        for key in data:
            if key == 'product':
                continue
            config[key] = data[key]

        bool_config = ['price_update_for_increase']
        for key in bool_config:
            config[key] = (key in data)

        # remove values if update is not selected
        if config['alert_price_change'] != 'update':
            config['price_update_method'] = ''
            config['price_update_for_increase'] = ''

        product.config = json.dumps(config)
        product.save()

        return self.api_success()

    def get_custom_tracking_url(self, request, user, data):
        try:
            store = self.store_model.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        custom_tracking = None
        tracking_config_key = 'aftership_domain' if self.is_shopify else f'{self.store_slug}_custom_tracking'
        tracking_config = user.models_user.get_config(tracking_config_key)
        if tracking_config and type(tracking_config) is dict:
            custom_tracking = tracking_config.get(str(store.id))

        return self.api_success({
            'tracking_url': custom_tracking,
            'store': store.id,
            'carriers': self.helper.get_store_tracking_carriers(store)
        })

    def post_custom_tracking_url(self, request, user, data):
        try:
            store = self.store_model.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        if not user.can('edit_settings.sub'):
            raise PermissionDenied()

        custom_tracking_key = str(store.id)
        tracking_config_key = 'aftership_domain' if self.is_shopify else f'{self.store_slug}_custom_tracking'
        tracking_config = user.models_user.get_config(tracking_config_key)
        if not tracking_config:
            tracking_config = {}
        elif type(tracking_config) is not dict:
            raise Exception('Custom domains is not a dict')

        if data.get('tracking_url'):
            tracking_config[custom_tracking_key] = data.get('tracking_url')
        else:
            if custom_tracking_key in tracking_config:
                del tracking_config[custom_tracking_key]

        user.models_user.set_config(tracking_config_key, tracking_config)

        return self.api_success()

    def get_currency(self, request, user, data):
        try:
            store = self.store_model.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        return self.api_success({
            'currency': store.currency_format or '',
            'store': store.id
        })

    def post_currency(self, request, user, data):
        try:
            store = self.store_model.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        if not user.can('edit_settings.sub'):
            raise PermissionDenied()

        if '{{' in data.get('currency'):
            store.currency_format = data.get('currency')
        else:
            if not data.get('currency'):
                currency = '$'
            else:
                currency = data.get('currency')
            store.currency_format = '{}{{{{amount}}}}'.format(currency)
        store.save()

        return self.api_success()

    def post_sync_with_supplier(self, request, user, data):
        product = self.product_model.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        limit_key = 'product_inventory_sync_{}_{}_{}'.format(self.store_slug, product.id, product.default_supplier.id)

        if cache.get(limit_key):
            return self.api_error('Sync is in progress', status=422)

        if product.is_connected:
            self.helper.sync_product_quantities(product.id)
        else:
            return self.api_error('Product is not connected', status=422)

        cache.set(limit_key, True, timeout=500)

        return self.api_success()

    def post_add_extra_store(self, request, user, data):
        store_id = data.get('store_id')
        store_type = data.get('store_type')
        store_model = get_store_model(store_type)
        try:
            store = store_model.objects.get(id=store_id)
            permissions.user_can_view(user, store)
        except store_model.DoesNotExist:
            return self.api_error('Store not found', status=404)

        can_add, total_allowed, user_count = permissions.can_add_store(user)
        stores_count = user.profile.get_stores_count()

        if user.profile.plan.is_stripe() \
                and not user.profile.plan.is_paused \
                and total_allowed > -1 \
                and total_allowed < stores_count:

            extra_store_model = get_extra_model_from_store(store)
            extra_store_model.objects.create(
                user=user,
                store=store,
                period_start=timezone.now(),
            )

            return self.api_success()

        return self.api_error('Store can not be added', status=403)

    def post_add_extra_subuser(self, request, user, data):
        subuser_id = data.get('subuser_id')
        try:
            subuser = User.objects.get(id=subuser_id)
        except User.DoesNotExist:
            return self.api_error('User not found', status=404)

        if user.is_subuser \
                and not subuser.profile.subuser_parent == user:
            raise permissions.PermissionDenied()

        can_add, total_allowed, user_count = permissions.can_add_subuser(user)
        subusers_count = user.profile.get_sub_users_count()

        if user.profile.plan.is_stripe() \
                and not user.profile.plan.is_paused \
                and total_allowed > -1 \
                and total_allowed < subusers_count:

            ExtraSubUser.objects.create(
                user=user,
                period_start=timezone.now(),
            )

            return self.api_success()

        return self.api_error('Subuser can not be added', status=403)

    def post_add_user_upload(self, request, user, data):
        try:
            product = self.product_model.objects.get(id=data.get('product'))
            permissions.user_can_edit(user, product)
        except ObjectDoesNotExist:
            return self.api_error('Product not found.', status=404)
        #
        try:
            product = self.product_model.objects.get(id=data.get('product'))
            permissions.user_can_edit(user, product)

        except ObjectDoesNotExist:
            return self.api_error('Product not found')

        upload = get_user_upload_model(self.store_slug).objects.create(
            user=user.models_user,
            product=product,
            url=data.get('url'))

        upload.save()

        permissions.user_can_add(user, upload)

        return self.api_success()
