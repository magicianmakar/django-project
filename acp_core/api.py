import json

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.forms.models import model_to_dict
from django.urls import reverse
from django.utils.text import slugify

from addons_core.models import Addon
from leadgalaxy.models import AdminEvent, AppPermission, FeatureBundle, GroupPlan
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import app_link, jwt_encode


def check_user_permission(user):
    if not user.is_superuser and not user.is_staff:
        raise PermissionDenied()


class ACPApi(ApiResponseMixin):
    http_method_names = ['get', 'post', 'delete']

    def delete_addon(self, request, user, data):
        check_user_permission(user)

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
        check_user_permission(user)

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
        check_user_permission(user)

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
        check_user_permission(user)

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
        check_user_permission(user)

        target_user = User.objects.get(id=data.get('user'))

        if target_user.is_superuser or target_user.is_staff:
            return self.api_error(f'Can not login as {target_user.email} (Staff account)', 422)

        token = jwt_encode({'id': target_user.id}, expire=1)

        link = app_link(reverse('sudo_login'), token=token)

        AdminEvent.objects.create(
            user=user,
            event_type='generate_login_as_user',
            target_user=user,
            data=json.dumps({'token': token}))

        return self.api_success({
            'url': link
        })

    def post_add_permission(self, request, user, data):
        check_user_permission(user)

        perm, created = AppPermission.objects.get_or_create(name=data['name'])
        perm.description = data['desc']
        perm.save()

        if data.get('bundle') == 'true':
            bundle = FeatureBundle.objects.create(title=f"{data['desc']} Bundle", slug=slugify(data['name']), hidden_from_user=True)
            bundle.permissions.add(perm)

        return self.api_success({'data': data})

    def get_plans(self, request, user, data):
        check_user_permission(user)

        plans = []
        for plan in GroupPlan.objects.all().select_related('stripe_plan').prefetch_related('permissions'):
            p = model_to_dict(plan, exclude=['goals'])
            permissions = []
            for perm in plan.permissions.all():
                if perm.name.endswith('.view'):
                    continue

                permissions.append(model_to_dict(perm))

            p.update({
                'description': plan.get_description(),
                'price': plan.get_price(),
                'active': plan.revision == settings.PLAN_REVISION,
                'permissions': permissions,
                'parent_plan': model_to_dict(plan.parent_plan, exclude=['goals']) if plan.parent_plan else None,
            })

            plans.append(p)

        active_plan = sorted(filter(lambda x: x['active'], plans), key=lambda x: x['id'])
        non_active_plan = sorted(filter(lambda x: not x['active'], plans), key=lambda x: x['id'])

        if request.GET.get('active') == 'true':
            plans = active_plan
        else:
            plans = [*active_plan, *non_active_plan]

        return self.api_success({'plans': plans})
