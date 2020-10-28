import re
from urllib.parse import parse_qs, urlparse

from django.template.defaultfilters import slugify
from django.db.models import Q
from django.shortcuts import get_object_or_404

from product_common.lib.views import upload_image_to_aws

from lib.exceptions import capture_exception
from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import safe_str

from .models import Category, Addon, AddonBilling, AddonUsage
from .utils import cancel_addon_usages


class AddonsApi(ApiResponseMixin):

    def post_add(self, request, user, data):
        if not request.user.can('addons_edit.use'):
            raise permissions.PermissionDenied()

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

    def post_edit(self, request, user, data):
        if not request.user.can('addons_edit.use'):
            raise permissions.PermissionDenied()

        addon = Addon.objects.get(id=data['addon-id'])
        addon.title = data['addon-title']
        addon.short_description = data['addon-short']
        addon.description = data['addon-description']
        addon.faq = data['addon-faq']
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

        existing_benefits = addon.get_key_benefits()
        benefits = []
        for i in range(0, 3):
            banner = request.FILES.get(f'addon-key-banner-{i}', None)
            if banner:
                banner_url = upload_image_to_aws(banner, f'key_benefit_banner_{i}', user.id)
            else:
                banner_url = existing_benefits[i]['banner']

            benefits.append({
                'id': i,
                'title': data[f'addon-key-title-{i}'],
                'description': data[f'addon-key-description-{i}'],
                'banner': banner_url,
            })

        addon.set_key_benefits(benefits)
        addon.save()

        return self.api_success()

    def post_install(self, request, user, data):
        # TODO: remove this when we allow multiple billing options for addons
        if 'billing' not in data:
            billing = get_object_or_404(Addon, id=data['addon']).billings.first()
            if billing is None:
                raise permissions.PermissionDenied()
        else:
            billing = AddonBilling.objects.select_related('addon').get(id=data['billing'])

        if billing.addon.action_url:
            return self.api_success({'redirect_url': billing.addon.action_url})

        if not user.profile.plan.support_addons:
            return self.api_error("Your plan doesn't support adding Addons", 422)

        if user.profile.addons.filter(id=billing.addon.id).exists():
            return self.api_error("Addon is already installed on your account", 422)

        if user.is_subuser:
            return self.api_error("Sub users can not install Addons", 403)

        if billing.addon.variant_from or billing.addon.variants.exists():
            variations_id = billing.addon.variant_from_id or billing.addon.id

            variations = Addon.objects.filter(
                Q(variant_from=variations_id) | Q(id=variations_id)
            )
            cancel_addon_usages(AddonUsage.objects.filter(
                user=user,
                billing__addon__in=variations,
                cancelled_at__isnull=True,
            ))

        AddonUsage.objects.get_or_create(
            user=user.models_user,
            billing=billing,
            cancelled_at__isnull=True
        )

        user.profile.addons.add(billing.addon)

        return self.api_success()

    def post_uninstall(self, request, user, data):
        addon = Addon.objects.get(id=data['addon'])

        if not user.profile.addons.filter(id=addon.id).exists():
            return self.api_error("Addon is not installed on your account", 422)

        if user.is_subuser:
            return self.api_error("Sub users can not install Addons", 403)

        cancel_addon_usages(AddonUsage.objects.filter(
            user=user,
            billing__addon=addon,
            cancelled_at__isnull=True,
        ))

        return self.api_success()
