import json

import requests

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.forms.models import model_to_dict
from django.urls import reverse
from django.utils.text import slugify
from django.utils.crypto import get_random_string

from addons_core.models import Addon
from leadgalaxy.models import AdminEvent, AppPermission, AppPermissionTag, FeatureBundle, GroupPlan
from leadgalaxy.utils import aws_s3_upload
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

        include_view = request.GET.get('view') == 'true'
        top_level = request.GET.get('top') == 'true'

        plans = []
        for plan in GroupPlan.objects.all().select_related('stripe_plan').prefetch_related('permissions', 'permissions__tags'):
            if plan.parent_plan_id and top_level:
                continue

            p = model_to_dict(plan, exclude=['goals'])
            permissions = []
            for perm in plan.permissions.all():
                if not include_view and perm.name.endswith('.view'):
                    continue

                permissions.append(perm.to_json())

            p.update({
                'description': plan.get_description(),
                'price': plan.get_price(),
                'active': plan.revision == settings.PLAN_REVISION,
                'permissions': permissions,
                'parent_plan': model_to_dict(plan.parent_plan, exclude=['goals', 'permissions']) if plan.parent_plan else None,
            })

            plans.append(p)

        active_plan = sorted(filter(lambda x: x['active'], plans), key=lambda x: x['id'])
        non_active_plan = sorted(filter(lambda x: not x['active'], plans), key=lambda x: x['id'])

        if request.GET.get('active') == 'true':
            plans = active_plan
        else:
            plans = [*active_plan, *non_active_plan]

        return self.api_success({
            'plans': plans,
            'tags': [tag.to_json() for tag in AppPermissionTag.objects.all()]
        })

    def get_permissions(self, request, user, data):
        check_user_permission(user)

        include_view = request.GET.get('view') == 'true'
        permissions = []
        for perm in AppPermission.objects.all().prefetch_related('tags').order_by('id'):
            if include_view or not perm.name.endswith('.view'):
                permissions.append(perm.to_json())

        return self.api_success({
            'permissions': permissions,
            'tags': [tag.to_json() for tag in AppPermissionTag.objects.all()]
        })

    def post_remove_permission_from_plan(self, request, user, data):
        check_user_permission(user)

        plan = GroupPlan.objects.get(id=data['plan'])
        perm = AppPermission.objects.get(id=data['permission'])

        plan.permissions.remove(perm)

        return self.api_success()

    def post_add_permissions(self, request, user, data):
        check_user_permission(user)

        plan = GroupPlan.objects.get(id=data['plan'])
        permissions = AppPermission.objects.filter(id__in=data['permissions'])

        plan.permissions.add(*permissions)

        return self.api_success()

    def post_remove_permissions(self, request, user, data):
        check_user_permission(user)

        permission = AppPermission.objects.filter(id=data['permission'])
        permission.delete()

        return self.api_success()

    def post_permission_image_upload(self, request, user, data):
        check_user_permission(user)

        permission = AppPermission.objects.get(id=data['permission'])
        upload_file = request.FILES['file']
        s3_key = f'permission_images/{get_random_string(length=10)}/{upload_file.name}'

        url = aws_s3_upload(s3_key, fp=upload_file)

        permission.add_image(url)
        permission.save()

        return self.api_success({
            'url': url
        })

    def get_permission_tags(self, request, user, data):
        check_user_permission(user)

        return self.api_success({
            'tags': [tag.to_json() for tag in AppPermissionTag.objects.all()]
        })

    def post_permission_tag(self, request, user, data):
        check_user_permission(user)

        tag = AppPermissionTag.objects.create(
            name=data['name'],
            description=data['description'],
            slug=slugify(data['name']),
        )

        return self.api_success({
            'tag': tag.to_json()
        })

    def post_permission_edit(self, request, user, data):
        check_user_permission(user)

        permission = AppPermission.objects.get(id=data['id'])
        permission.name = data['name']
        permission.description = data['description']
        permission.notes = data['notes']
        permission.image_url = ','.join(data['images']) if data.get('images') else ''

        permission.tags.clear()
        if data.get('tags'):
            for tag in AppPermissionTag.objects.filter(id__in=[t['id'] for t in data['tags']]):
                permission.tags.add(tag)

        permission.save()

        return self.api_success({
            'permission': permission.to_json()
        })

    def post_sub_affiliate(self, request, user, data):
        check_user_permission(user)

        user: User = User.objects.get(id=data['user'])

        # Add user to First Promoter
        rep = requests.post(
            'https://firstpromoter.com/api/v1/promoters/create',
            json={
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'website': settings.APP_URL,
                'custom_field': {
                    'user_id': user.id,
                }
            },
            headers={
                'x-api-key': settings.FIRST_PROMOTER_API_KEY,
            }
        )

        if rep.ok:
            return self.api_success()
        else:
            return self.api_error('Could not add user to First Promoter')

    def post_affilaite_upgrade(self, request, user, data):
        check_user_permission(user)

        user: User = User.objects.get(id=data['user'])
        promoter_id = data['promoter']

        # Add user to First Promoter
        rep = requests.post(
            'https://firstpromoter.com/api/v1/promoters/move_to_campaign',
            json={
                'id': promoter_id,
                'destination_campaign_id': '6239',
            },
            headers={
                'x-api-key': settings.FIRST_PROMOTER_API_KEY,
            }
        )

        if rep.ok:
            return self.api_success()
        else:
            return self.api_error('Could not add user to First Promoter')
