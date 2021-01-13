import json

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied

from addons_core.models import Addon
from leadgalaxy.models import AdminEvent
from shopified_core.mixins import ApiResponseMixin


class ACPApi(ApiResponseMixin):
    http_method_names = ['delete']

    def delete_addon(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))
        addon = Addon.objects.get(id=data.get('addon'))

        AdminEvent.objects.create(
            user=user,
            target_user=target_user,
            event_type='delete_addon',
            data=json.dumps({'addon': addon.title}))

        target_user.profile.addons.remove(addon)

        return self.api_success()
