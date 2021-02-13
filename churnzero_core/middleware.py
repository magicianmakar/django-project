from churnzero_core.utils import set_churnzero_account
from lib.exceptions import capture_exception
from shopified_core.utils import last_executed


class ChurnZeroMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.is_ajax() and '/api/' not in request.path and request.user.is_authenticated:
            if not last_executed(f'churn_zero_mw_{request.user.id}', 3600):
                try:
                    set_churnzero_account(request.user.models_user)
                except:
                    capture_exception(level='warning')

        return self.get_response(request)
