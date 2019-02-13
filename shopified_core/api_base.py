from django.core.exceptions import PermissionDenied
from django.views.generic import View

from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin


class ApiBase(ApiResponseMixin, View):
    board_model = None

    def __init__(self):
        super(ApiBase, self).__init__()
        self.assert_configured()

    def assert_configured(self):
        assert self.board_model, 'Boards Model is not set'

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

        board = self.board_model(title=board_name, user=user.models_user)
        permissions.user_can_add(user, board)

        board.save()

        return self.api_success({
            'board': {
                'id': board.id,
                'title': board.title
            }
        })

    def post_board_favorite(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        board = self.board_model.objects.get(id=data.get('board'))
        permissions.user_can_edit(user, board)

        board.favorite = bool(data.get('favorite'))
        board.save()

        return self.api_success()
