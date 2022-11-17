from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView, View
from django.http import HttpResponseRedirect

from alibaba_core.utils import get_access_token_url as get_alibaba_access_token_url
from ebay_core.utils import EbayUtils, get_ebay_currencies_list
from fp_affiliate.settings import FIRST_PROMOTER_DASHBOARD_URL
from goals.utils import get_dashboard_user_goals
from leadgalaxy.models import DashboardVideo, DescriptionTemplate, GroupPlan, PriceMarkupRule
from leadgalaxy.tasks import fulfullment_service_check
from lib.exceptions import capture_message
from shopified_core import permissions
from shopified_core.mocks import get_mocked_config_alerts
from shopified_core.shipping_helper import get_counrties_list
from shopified_core.utils import jwt_encode
from shopified_core.exceptions import RedirectException
from aliexpress_core.models import AliexpressAccount
from profit_dashboard.views import index
from profits.utils import get_store_from_request
from commercehq_core.views import ProfitDashboardView as CHQProfitDashboardView
from woocommerce_core.views import ProfitDashboardView as WooProfitDashboardView
from groovekart_core.views import ProfitDashboardView as GKartProfitDashboardView
from bigcommerce_core.views import ProfitDashboardView as BigCommerceProfitDashboardView
from ebay_core.views import ProfitDashboardView as EBayProfitDashboardView
from facebook_core.views import ProfitDashboardView as FBProfitDashboardView
from google_core.views import ProfitDashboardView as GoogleProfitDashboardView


class HomePageMixing(TemplateView):
    @method_decorator(login_required)
    @method_decorator(xframe_options_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except RedirectException as e:
            return HttpResponseRedirect(e.url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        user = self.request.user

        config = user.models_user.profile.get_config()

        if user.get_config('__plan'):
            free_plan = GroupPlan.objects.get(id=user.get_config('__plan'))
            if user.profile.plan != free_plan and user.profile.plan.free_plan:
                user.profile.change_plan(free_plan)

        aliexpress_shipping_method = config.get('aliexpress_shipping_method')
        epacket_shipping = config.get('epacket_shipping')

        if epacket_shipping:
            aliexpress_shipping_method = 'EMS_ZX_ZX_US'

        can_add, total_allowed, user_count = permissions.can_add_store(user)

        extra_stores = can_add and user.profile.plan.is_stripe() and \
            user.profile.get_stores_count() >= total_allowed != -1

        add_store_btn = not user.is_subuser \
            and (can_add or user.profile.plan.extra_stores) \
            and not user.profile.from_shopify_app_store()

        templates = DescriptionTemplate.objects.filter(user=user.models_user).defer('description')
        markup_rules = PriceMarkupRule.objects.filter(user=user.models_user)

        user_goals = get_dashboard_user_goals(self.request.user)
        videos = DashboardVideo.objects.filter(is_active=True, plans=user.models_user.profile.plan)
        platform_videos = {t[0]: [] for t in DashboardVideo.STORE_TYPES}
        for video in videos:
            platform_videos[video.store_type].append(video)

        upsell_alerts = False
        if not user.can('price_changes.use'):
            upsell_alerts = True
            config.update(get_mocked_config_alerts())

        if FIRST_PROMOTER_DASHBOARD_URL and not user.is_subuser and not self.request.session.get('is_hijacked_user'):
            if user.profile.plan.is_free:
                if not user.get_config('__fp_partners_redirect'):
                    user.set_config('__fp_partners_redirect', True)
                    raise HttpResponseRedirect(url=FIRST_PROMOTER_DASHBOARD_URL)

        fulfullment_service_check.apply_async(args=[user.id], queue='priority_high', expires=200)

        ctx.update({
            'config': config,
            'epacket_shipping': epacket_shipping,
            'aliexpress_shipping_method': aliexpress_shipping_method,
            'extra_stores': extra_stores,
            'add_store_btn': add_store_btn,
            'templates': templates,
            'markup_rules': markup_rules,
            'user_statistics': cache.get('user_statistics_{}'.format(user.id)),
            'user_goals': user_goals,
            'platform_videos': platform_videos,
            'upsell_alerts': upsell_alerts,
            'alibaba_login_url': get_alibaba_access_token_url(user.models_user),
            'aliexpress_accounts': AliexpressAccount.objects.filter(user=user.models_user),
        })

        return ctx


class HomePageView(HomePageMixing):
    template_name = 'home/index.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx['page'] = 'index'
        ctx['breadcrumbs'] = ['Stores']

        return ctx


class SettingsPageView(HomePageMixing):
    template_name = 'home/settings.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx['page'] = 'settings'
        ctx['breadcrumbs'] = ['Settings']

        # eBay Settings
        ctx['ebay_settings'] = EbayUtils(self.request.user).get_ebay_user_settings_config()
        ctx['countries'] = get_counrties_list()
        ctx['currencies'] = get_ebay_currencies_list()
        return ctx


class DashboardView(HomePageMixing):
    template_name = 'home/dashboard.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.profile.plan.is_research:
            return super().dispatch(request, *args, **kwargs)

        store_type = kwargs.get('store_type') or 'shopify'
        store = get_store_from_request(request, store_type)
        if store:
            store_type = store.store_type
            if store_type == 'chq':
                view = CHQProfitDashboardView.as_view()(request, *args, from_dashboard=True, **kwargs)
            elif store_type == 'woo':
                view = WooProfitDashboardView.as_view()(request, *args, from_dashboard=True, **kwargs)
            elif store_type == 'gkart':
                view = GKartProfitDashboardView.as_view()(request, *args, from_dashboard=True, **kwargs)
            elif store_type == 'bigcommerce':
                view = BigCommerceProfitDashboardView.as_view()(request, *args, from_dashboard=True, **kwargs)
            elif store_type == 'ebay':
                view = EBayProfitDashboardView.as_view()(request, *args, from_dashboard=True, **kwargs)
            elif store_type == 'fb':
                view = FBProfitDashboardView.as_view()(request, *args, from_dashboard=True, **kwargs)
            elif store_type == 'google':
                view = GoogleProfitDashboardView.as_view()(request, *args, from_dashboard=True, **kwargs)
            else:
                view = index(request, from_dashboard=True)

            return view

        try:
            store = request.user.profile.get_stores(request)['all'][0]
        except:
            store = None

        if store:
            return redirect('dashboard', store_type=store.store_type)

        return index(request, from_dashboard=True)


class GotoPage(View):
    def get_failure_url(self):
        messages.warning(self.request, 'Please connect your store first.')
        return redirect('/')

    def get(self, request, url_name='index'):
        user = request.user
        if not user.is_authenticated:
            return self.get_failure_url()

        try:
            stores = request.user.profile.get_stores(self.request)['all']
        except:
            stores = []

        if not stores:
            return self.get_failure_url()

        for store in stores:
            try:
                url = store.get_page_url(url_name)
                return redirect(url)
            except:
                pass

        messages.error(request, 'Could not find the requested page')

        capture_message('Redirect not found', extra={
            'url_name': url_name,
        })

        return store.get_page_url('index')


class RoadMap(HomePageMixing):
    template_name = 'home/roadmap.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        user = self.request.user.models_user
        user_data = {
            'email': user.email,
            'name': f'{user.first_name} {user.last_name[:1]}',
        }

        encoded_jwt = jwt_encode(user_data, key=settings.LOOPEDIN_SSO_KEY)
        context['loopedin_token'] = encoded_jwt
        return context
