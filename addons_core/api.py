import arrow
from django.db.models import Q
from django.shortcuts import get_object_or_404

from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin
from metrics.tasks import update_activecampaign_addons

from .models import Addon, AddonBilling, AddonUsage
from .utils import (
    get_shopify_subscription,
    has_shopify_limit_exceeded,
    create_shopify_subscription,
    cancel_addon_usages,
)


class AddonsApi(ApiResponseMixin):

    def post_install(self, request, user, data):
        # TODO: remove this when we allow multiple billing options for addons
        if 'billing' not in data:
            billing = get_object_or_404(Addon, id=data['addon']).billings.first()
            if billing is None:
                raise permissions.PermissionDenied()
        else:
            billing = AddonBilling.objects.select_related('addon').get(id=data['billing'])

        if not user.profile.plan.support_addons:
            return self.api_error("Your plan doesn't support adding Addons", 422)

        if billing.addon.action_url:
            return self.api_success({'redirect_url': billing.addon.action_url})

        if not user.is_stripe_customer() and not user.profile.from_shopify_app_store():
            return self.api_error("Your plan doesn't support adding Addons yet", 403)

        elif user.profile.from_shopify_app_store():
            # Yearly plans use ApplicationCharge rather than RecurringApplicationCharge
            charge = get_shopify_subscription(user)
            if not charge:
                store = user.profile.get_shopify_stores().first()
                result = create_shopify_subscription(store, billing)
                if not result:
                    return self.api_error("Your plan doesn't support installing addons", status=403)
                elif 'error' not in result:
                    return self.api_success({'shopify': result})
                else:
                    return self.api_error(result, status=403)

            limit_exceeded = has_shopify_limit_exceeded(user.models_user, charge=charge)
            if limit_exceeded:
                return self.api_success({'shopify': {'limit_exceeded_link': limit_exceeded}})

        active_until_period_end = AddonUsage.objects.filter(
            user=user.models_user,
            billing=billing,
            is_active=True,
            cancelled_at__isnull=False,
            cancel_at__gt=arrow.get().date(),
        )
        if user.profile.addons.filter(id=billing.addon.id).exists() \
                and len(active_until_period_end) == 0:
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

        if len(active_until_period_end) > 0:
            addon_usage = active_until_period_end[0]
            addon_usage.cancelled_at = None
            addon_usage.cancel_at = None
            addon_usage.next_billing = addon_usage.get_next_billing_date()
            addon_usage.save()

        else:
            AddonUsage.objects.get_or_create(
                user=user.models_user,
                billing=billing,
                cancelled_at__isnull=True
            )

            user.profile.addons.add(billing.addon)

        update_activecampaign_addons.apply_async(args=[user.id], countdown=10)

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

        update_activecampaign_addons.apply_async(args=[user.id], countdown=10)

        return self.api_success()
