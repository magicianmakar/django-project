from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic.base import RedirectView

from shopified_core.utils import jwt_encode


@method_decorator(login_required, name='dispatch')
class LoopedinSSO(RedirectView):

    def get_redirect_url(self, *args, **kwargs):
        return_url = self.request.GET.get('returnURL')
        user = self.request.user.models_user
        user_data = {
            'email': user.email,
            'name': f'{user.first_name} {user.last_name[:1]}',
        }

        encoded_jwt = jwt_encode(user_data, key=settings.LOOPEDIN_SSO_KEY)
        redirect_url = f'{return_url}?token={encoded_jwt}'

        return redirect_url
