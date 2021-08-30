import json
import arrow
import jwt

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from addons_core.models import Addon
from leadgalaxy.models import AdminEvent
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import app_link


class ACPApi(ApiResponseMixin):
    http_method_names = ['post', 'delete']

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

    def post_deactivate_account(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))

        AdminEvent.objects.create(
            user=user,
            target_user=target_user,
            event_type='deactivate_account',
            data=json.dumps({'user': target_user.id}))

        target_user.is_active = False
        target_user.save()

        return self.api_success()

    def post_activate_account(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))

        AdminEvent.objects.create(
            user=user,
            target_user=target_user,
            event_type='activate_account',
            data=json.dumps({'user': target_user.id}))

        target_user.is_active = True
        target_user.save()

        return self.api_success()

    def post_toggle_plod(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))

        if target_user.is_subuser:
            return self.api_error("Sub user account can not be changed", 422)

        profile = target_user.profile
        if profile.private_label:
            return self.api_error("User is from the separate Shopify Private Label App", 422)

        AdminEvent.objects.create(
            user=user,
            target_user=target_user,
            event_type='toggle_plod',
            data=json.dumps({'user': target_user.id}))

        profile.dropified_private_label = not profile.dropified_private_label
        profile.save()

        return self.api_success()

    def post_login_as(self, request, user, data):
        if not user.is_superuser and not user.is_staff:
            raise PermissionDenied()

        target_user = User.objects.get(id=data.get('user'))

        if target_user.is_superuser or target_user.is_staff:
            return self.api_error(f'Can not login as {target_user.email} (Staff account)', 422)

        token = jwt.encode({
            'id': target_user.id,
            'exp': arrow.utcnow().replace(hours=1).timestamp
        }, settings.API_SECRECT_KEY, algorithm='HS256')

        link = app_link(reverse('sudo_login'), token=token)

        AdminEvent.objects.create(
            user=user,
            event_type='generate_login_as_user',
            target_user=user,
            data=json.dumps({'token': token}))

        return self.api_success({
            'url': link
        })
