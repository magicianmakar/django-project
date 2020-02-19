from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.generic import View
from django.views.decorators.clickjacking import xframe_options_exempt

from shopified_core import permissions
from leadgalaxy.models import DescriptionTemplate, PriceMarkupRule, DashboardVideo
from goals.utils import get_dashboard_user_goals

from .context_processors import all_stores


@login_required
@xframe_options_exempt
def home_page_view(request):
    user = request.user

    config = user.models_user.profile.get_config()

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
    videos = DashboardVideo.objects.filter(is_active=True)[:4]

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
        'selected_menu': 'account:stores',
        'user_statistics': cache.get('user_statistics_{}'.format(user.id)),
        'breadcrumbs': ['Stores'],
        'user_goals': user_goals,
        'videos': videos,
    })


class GotoPage(View):
    def get_failure_url(self, url_name):
        messages.warning(self.request, 'Please connect your store first.')
        return redirect('/')

    def get(self, request, url_name='index'):
        user = request.user
        if not user.is_authenticated:
            return self.get_failure_url(url_name)

        try:
            stores = all_stores(self.request)['user_stores']['all']
        except:
            stores = []

        if not stores:
            return self.get_failure_url(url_name)

        store = stores[0]
        url = store.get_page_url(url_name)
        return redirect(url)
