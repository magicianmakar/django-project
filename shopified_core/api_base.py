import simplejson as json

from django.views.generic import View
from django.utils.decorators import method_decorator
from django.db.models import ObjectDoesNotExist

from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import dict_val

from shopified_core.decorators import HasSubuserPermission


class ApiBase(ApiResponseMixin, View):
    board_model = None

    def __init__(self):
        super(ApiBase, self).__init__()
        self._assert_configured()

    def _assert_configured(self):
        assert self.board_model, 'Boards Model is not set'

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

        return self.api_success()
