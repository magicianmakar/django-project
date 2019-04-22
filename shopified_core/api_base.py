import simplejson as json
import arrow
import itertools

from raven.contrib.django.raven_compat.models import client as raven_client

from django.views.generic import View
from django.utils.decorators import method_decorator
from django.db.models import ObjectDoesNotExist, F
from django.http import JsonResponse
from django.core.cache import cache
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.db import transaction

from last_seen.models import LastSeen

from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import (
    dict_val,
    safe_int,
    safe_float,
    order_data_cache,
    order_phone_number,
    orders_update_limit,
    serializers_orders_track,
)
from shopified_core.shipping_helper import aliexpress_country_code_map, fix_fr_address

from shopified_core.decorators import HasSubuserPermission


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
                'Your current plan allow up to %d boards, currently you have %d boards.'
                % (total_allowed, user_count))

        board_name = data.get('title', '').strip()

        if not len(board_name):
            return self.api_error('Board name is required', status=501)

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
            if user.models_user.get_config('_static_shipping_address'):
                order['shipping_address'] = user.models_user.get_config('_static_shipping_address')

            if not order['shipping_address'].get('address2'):
                order['shipping_address']['address2'] = ''

            if order['shipping_address']['country_code'] == 'FR':
                order['shipping_address'] = fix_fr_address(order['shipping_address'])

            order['shipping_address']['country_code'] = aliexpress_country_code_map(order['shipping_address']['country_code'])

            order['ordered'] = False
            order['fast_checkout'] = user.get_config('_fast_checkout', True)
            order['solve'] = user.models_user.get_config('aliexpress_captcha', False)

            phone = order['order']['phone']
            if type(phone) is dict:
                phone_country, phone_number = order_phone_number(request, user.models_user, phone['number'], phone['country'])
                order['order']['phone'] = phone_number
                order['order']['phoneCountry'] = phone_country

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
                raven_client.captureException()

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

        order_tracks = self.order_track_model.objects.filter(user=user.models_user, hidden=False) \
                           .defer('data') \
                           .order_by('updated_at')

        created_at_start = None
        created_at_end = None
        created_at_max = arrow.now().replace(days=-30).datetime  # Always update orders that are max. 30 days old
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

            if created_at_start >= created_at_max:
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

        source_id = safe_int(dict_val(data, ['shopify', 'woocommerce', 'gearbubble']))

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

    @method_decorator(HasSubuserPermission('save_for_later.sub'))
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
