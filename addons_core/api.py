import re
from urllib.parse import parse_qs, urlparse

from django.template.defaultfilters import slugify
from django.utils import timezone

from product_common.lib.views import upload_image_to_aws

from lib.exceptions import capture_exception
from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import safe_float, safe_int, safe_str

from .models import Addon, AddonUsage, Category


class AddonsApi(ApiResponseMixin):
    def post_add(self, request, user, data):
        if request.user.can('addons_edit.use'):
            title = safe_str(data.get('title')).strip()
            if not title:
                return self.api_error("Addon title can not be empty", status=422)

            addon = Addon.objects.create(
                title=title,
                slug=slugify(title)
            )

            return self.api_success({
                'id': addon.id,
                'slug': addon.slug
            })
        else:
            raise permissions.PermissionDenied()

    def post_edit(self, request, user, data):
        if request.user.can('addons_edit.use'):
            addon = Addon.objects.get(id=data['addon-id'])
            addon.title = data['addon-title']
            addon.short_description = data['addon-short']
            addon.description = data['addon-description']
            addon.faq = data['addon-faq']
            addon.monthly_price = safe_float(data['addon-price'])
            addon.trial_period_days = safe_int(data['addon-trial-days'])
            addon.hidden = data['addon-status'] == 'draft'

            categories_ids = data['addon-categories'].split(',')
            categories = Category.objects.filter(id__in=categories_ids)
            addon.categories.clear()
            addon.categories.add(*categories)

            icon = request.FILES.get('addon-icon', None)
            if icon:
                addon.icon_url = upload_image_to_aws(icon, 'addon_icons', user.id)
            banner = request.FILES.get('addon-banner', None)
            if banner:
                addon.banner_url = upload_image_to_aws(banner, 'addon_banners', user.id)

            youtube_id = None
            if data['addon-youtube']:
                youtube_id = re.findall('youtube.com/embed/[^?#]+', data['addon-youtube'])
                if youtube_id:
                    youtube_id = youtube_id.pop().split('/').pop()

            if not youtube_id:
                try:
                    youtube_id = parse_qs(urlparse(data['addon-youtube']).query)['v'].pop()
                except KeyError:
                    youtube_id = urlparse(data['addon-youtube']).path.strip('/')
                except:
                    capture_exception(level='warning')

            addon.youtube_url = f'https://www.youtube.com/embed/{youtube_id}' if youtube_id else ''

            vimeo_id = None
            if data['addon-vimeo']:
                vimeo_id = re.findall('player.vimeo.com/video/[^?#]+', data['addon-vimeo'])
                if vimeo_id:
                    vimeo_id = vimeo_id.pop().split('/').pop()

            if not vimeo_id:
                try:
                    vimeo_id = urlparse(data['addon-vimeo']).path.strip('/')
                except:
                    capture_exception(level='warning')

            addon.vimeo_url = f'https://player.vimeo.com/video/{vimeo_id}' if vimeo_id else ''

            benfits = []
            for i in range(0, 3):
                benfits.append({
                    'id': i,
                    'title': data[f'addon-key-title-{i}'],
                    'description': data[f'addon-key-description-{i}'],
                    'banner': data[f'addon-key-banner-{i}'],
                })

            addon.set_key_benfits(benfits)
            addon.save()

            return self.api_success()
        else:
            raise permissions.PermissionDenied()

    def post_install(self, request, user, data):
        addon = Addon.objects.get(id=data['addon'])

        if not user.profile.plan.support_addons:
            return self.api_error("Your plan doesn't support adding Addons", 422)

        if user.profile.addons.filter(id=addon.id).exists():
            return self.api_error("Addon is already installed on your account", 422)

        AddonUsage.objects.create(
            user=user,
            addon=addon,
        )

        user.profile.addons.add(addon)

        return self.api_success()

    def post_uninstall(self, request, user, data):
        addon = Addon.objects.get(id=data['addon'])

        if not user.profile.addons.filter(id=addon.id).exists():
            return self.api_error("Addon is not installed on your account", 422)

        AddonUsage.objects.filter(
            user=user,
            addon=addon,
        ).update(
            is_active=False,
            cancelled_at=timezone.now()
        )

        user.profile.addons.remove(addon)

        return self.api_success()
