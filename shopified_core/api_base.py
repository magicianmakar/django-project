from django.core.exceptions import PermissionDenied
from django.views.generic import View

from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin


class ApiBase(ApiResponseMixin, View):
    board_model = None

    def post_board_favorite(self, request, user, data):
        if not user.can('edit_product_boards.sub'):
            raise PermissionDenied()

        assert self.board_model is not None
        board = self.board_model.objects.get(id=data.get('board'))
        permissions.user_can_edit(user, board)

        board.favorite = bool(data.get('favorite'))
        board.save()

        return self.api_success()
