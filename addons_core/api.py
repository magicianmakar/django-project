from django.utils import timezone
from django.template.defaultfilters import slugify

from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import safe_str, safe_float
from .models import Addon, AddonUsage


class AddonsApi(ApiResponseMixin):
    def post_add(self, request, user, data):
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
        addon = Addon.objects.get(id=data['addon-id'])
        addon.title = data['addon-title']
        addon.short_description = data['addon-short']
        addon.description = data['addon-description']
        addon.icon_url = data['addon-icon']
        addon.banner_url = data['addon-banner']
        addon.youtube_url = data['addon-youtube']
        addon.monthly_price = safe_float(data['addon-price'])
        addon.hidden = data['addon-status'] == 'draft'

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
