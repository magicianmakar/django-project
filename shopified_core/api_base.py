import simplejson as json

from django.views.generic import View
from django.utils.decorators import method_decorator
from django.db.models import ObjectDoesNotExist
from django.http import JsonResponse

from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import dict_val, safe_int, safe_float

from shopified_core.decorators import HasSubuserPermission


class ApiBase(ApiResponseMixin, View):
    board_model = None
    product_model = None
    order_track_model = None
    helper = None

    def __init__(self):
        super(ApiBase, self).__init__()
        self._assert_configured()

    def _assert_configured(self):
        assert self.board_model, 'Boards Model is not set'
        assert self.product_model, 'Product Model is not set'
        assert self.order_track_model, 'Order Track Model is not set'
        assert self.helper, 'Helper is not set'

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
