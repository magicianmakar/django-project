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

    def post_board_favorite(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        board = self.board_model.objects.get(id=data.get('board'))
        permissions.user_can_edit(user, board)

        board.favorite = bool(data.get('favorite'))
        board.save()

        return self.api_success()
