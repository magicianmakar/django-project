from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.generic import View
from django.views.decorators.clickjacking import xframe_options_exempt

from lib.exceptions import capture_message

from alibaba_core.utils import get_access_token_url as get_alibaba_access_token_url
from shopified_core import permissions
from shopified_core.utils import last_executed
from shopified_core.mocks import get_mocked_config_alerts
from leadgalaxy.models import DescriptionTemplate, PriceMarkupRule, DashboardVideo, GroupPlan
from leadgalaxy.shopify import ShopifyAPI
from goals.utils import get_dashboard_user_goals

from .context_processors import all_stores


@login_required
@xframe_options_exempt
def home_page_view(request):
    user = request.user

    config = user.models_user.profile.get_config()

    if user.get_config('__plan'):
        free_plan = GroupPlan.objects.get(id=user.get_config('__plan'))
        if user.profile.plan != free_plan and not user.profile.plan.free_plan:
            user.profile.change_plan(free_plan)

    aliexpress_shipping_method = config.get('aliexpress_shipping_method')
    epacket_shipping = config.get('epacket_shipping')

    if epacket_shipping:
        aliexpress_shipping_method = 'EMS_ZX_ZX_US'

    can_add, total_allowed, user_count = permissions.can_add_store(user)

    extra_stores = can_add and user.profile.plan.is_stripe() and \
        user.profile.get_stores_count() >= total_allowed and \
        total_allowed != -1

    add_store_btn = not user.is_subuser \
        and (can_add or user.profile.plan.extra_stores) \
        and not user.profile.from_shopify_app_store()

    templates = DescriptionTemplate.objects.filter(user=user.models_user).defer('description')
    markup_rules = PriceMarkupRule.objects.filter(user=user.models_user)

    user_goals = get_dashboard_user_goals(request.user)
    videos = DashboardVideo.objects.filter(is_active=True, plans=user.models_user.profile.plan)
    platform_videos = {t[0]: [] for t in DashboardVideo.STORE_TYPES}
    for video in videos:
        platform_videos[video.store_type].append(video)

    plan = user.models_user.profile.plan
    if plan.is_shopify() and not plan.is_free and not last_executed(f'recurring_charges_check_{user.models_user.id}', 3600):
        stores = user.profile.get_shopify_stores()
        if len(stores) == 0:
            capture_message(
                'Shopify Subscription - Missing Stores',
                level='warning',
                tags={
                    'user': user.models_user.email,
                    'store': 'none',
                    'count': len(stores)
                })
        elif len(stores) > 1:
            capture_message(
                'Shopify Subscription - Many Stores',
                level='warning',
                tags={
                    'user': user.models_user.email,
                    'store': 'none',
                    'count': len(stores)
                })
        else:
            try:
                charges = ShopifyAPI(stores[0])
                if not charges.recurring_charges(active=True):
                    capture_message(
                        'Shopify Subscription - Missing Subscription',
                        level='warning',
                        tags={
                            'user': user.models_user.email,
                            'store': 'none',
                            'count': len(stores)
                        })
            except:
                pass

    upsell_alerts = False
    if not user.can('price_changes.use'):
        upsell_alerts = True
        config.update(get_mocked_config_alerts())

    return render(request, 'home/index.html', {
        'config': config,
        'epacket_shipping': epacket_shipping,
        'aliexpress_shipping_method': aliexpress_shipping_method,
        'extra_stores': extra_stores,
        'add_store_btn': add_store_btn,
        'templates': templates,
        'markup_rules': markup_rules,
        'settings_tab': request.path == '/settings',
        'page': 'index',
        'user_statistics': cache.get('user_statistics_{}'.format(user.id)),
        'breadcrumbs': ['Stores'],
        'user_goals': user_goals,
        'platform_videos': platform_videos,
        'upsell_alerts': upsell_alerts,
        'alibaba_login_url': get_alibaba_access_token_url(user.models_user)
    })


class GotoPage(View):
    def get_failure_url(self):
        messages.warning(self.request, 'Please connect your store first.')
        return redirect('/')

    def get(self, request, url_name='index'):
        user = request.user
        if not user.is_authenticated:
            return self.get_failure_url()

        try:
            stores = all_stores(self.request)['user_stores']['all']
        except:
            stores = []

        if not stores:
            return self.get_failure_url()

        store = stores[0]
        url = store.get_page_url(url_name)
        return redirect(url)
