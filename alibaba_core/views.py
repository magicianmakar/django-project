import arrow
import requests
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import Http404
from django.shortcuts import redirect, reverse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.views.generic.base import RedirectView

from aliexpress_core.utils import get_store_data
from shopified_core import permissions
from shopified_core.utils import safe_int

from .models import AlibabaAccount
from .utils import TopAuthTokenCreateRequest, get_alibaba_account, get_search


@method_decorator(login_required, name='dispatch')
class AccessTokenRedirectView(RedirectView):
    permanent = True
    pattern_name = 'settings'

    def get_redirect_url(self, *args, **kwargs):
        auth_api = TopAuthTokenCreateRequest()
        token_data = auth_api.get_access_token(self.request.GET.get('code'))

        if token_data.get('error_msg'):
            error_question = ''
            if token_data.get('sub_code') == 'isv.param-authorization.code.invalid':
                error_question = 'Have you tried selecting an expiration date?'
            messages.error(self.request, f"{token_data.get('error_msg')} ({token_data.get('error_code')}). {error_question}")

            self.query_string = True  # Show alibaba code in params for CS
            return super().get_redirect_url(*args, **kwargs)

        user = self.request.user.models_user
        account, _ = AlibabaAccount.objects.update_or_create(user=user, defaults={
            'access_token': token_data['access_token'],
            'expired_at': arrow.get(token_data['expire_time'] / 1000).datetime,
            'alibaba_user_id': token_data['user_id'],
            'alibaba_email': token_data.get('email', ''),
        })
        account.allow_message_consumption()
        account.get_ecology_token(refresh=True)

        messages.success(self.request, "Your Dropified account is connected to Alibaba")
        return f"{super().get_redirect_url(*args, **kwargs)}#alibaba-settings"


class Products(TemplateView):
    template_name = 'alibaba/products.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('find_products.view'):
            if not request.user.can('find_products.use'):
                return redirect('aliexpress:products')
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get('q', '')
        page = safe_int(self.request.GET.get('page', 1))
        use_filters = self.request.GET.get('f', None)
        currency = self.request.GET.get('currency', 'USD')
        price_min = self.request.GET.get('price_min', '')
        price_max = self.request.GET.get('price_max', '')
        sort = self.request.GET.get('sort', '-order_count')

        account = get_alibaba_account(self.request.user)

        ranked_categories = cache.get('alibaba_ranked_categories', {})
        if not ranked_categories:
            ranked_categories = requests.get(
                settings.INSIDER_REPORT_HOST + 'dropshipping-api/ranked-categories/',
                verify=False
            ).json()
            cache.set('alibaba_ranked_categories', ranked_categories, timeout=600)

        cache_key = f'alibaba_ranked_products_{page}'
        if search_query:
            cache_key = f'{cache_key}_{search_query}'

        ranked_products = {}
        if not use_filters:
            ranked_products = cache.get(cache_key, {})
        if search_query and not ranked_products:
            api_url = 'https://dropshipping.alibaba.com/saas/ajax/product/search/query_product'
            params = {
                'search_query': search_query,
                'page': page,
                'currency': currency,
                'price_min': safe_int(price_min),
                'price_max': safe_int(price_max),
                'sort': sort,
            }
            ranked_products = get_search(api_url, **params)
            cache.set(cache_key, ranked_products, timeout=600)

        if not ranked_products:
            api_url = f'dropshipping-api/ranked-products?include_nontop=true&page={page}' \
                      f'&price_from={price_min}&price_to={price_max}'
            ranked_products = requests.get(
                settings.INSIDER_REPORT_HOST + api_url,
                verify=False,
            ).json()
            if sort.startswith('-'):
                ranked_products['results'] = sorted(ranked_products['results'], key=lambda x: x['total_quantities'], reverse=True)
            else:
                ranked_products['results'] = sorted(ranked_products['results'], key=lambda x: x['total_quantities'])
            cache.set(cache_key, ranked_products, timeout=600)

        if account.user == self.request.user:
            for product in ranked_products['results']:
                product['url'] = f'{product["url"]}?ecology_token={account.ecology_token}'

        store_data = get_store_data(self.request.user)

        paginator = {
            'show': True if len(ranked_products['results']) >= 20 else False,
            'current_page': page,
            'next_page': page + 1,
            'previous_page': page - 1,
        }

        context.update({
            'categories': ranked_categories,
            'products': ranked_products,
            'total_results': ranked_products['count'],
            'store_data': store_data,
            'paginator': paginator,
            'search_query': search_query,
        })

        return context


class CategoryProducts(TemplateView):
    template_name = 'alibaba/category_products.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('find_products.view'):
            if not request.user.can('find_products.use'):
                return redirect('aliexpress:products')
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get('q', '')
        page = safe_int(self.request.GET.get('page', 1))
        use_filters = self.request.GET.get('f', None)
        currency = self.request.GET.get('currency', 'USD')
        price_min = self.request.GET.get('price_min', '')
        price_max = self.request.GET.get('price_max', '')
        sort = self.request.GET.get('sort', '-order_count')

        account = get_alibaba_account(self.request.user)

        category_id = kwargs.get('category_id')
        category = ''

        ranked_categories = cache.get('alibaba_ranked_categories', {})
        if not ranked_categories:
            ranked_categories = requests.get(
                settings.INSIDER_REPORT_HOST + 'dropshipping-api/ranked-categories/',
                verify=False
            ).json()
            cache.set('alibaba_ranked_categories', ranked_categories, timeout=600)

        for entry in ranked_categories['results']:
            if str(entry['id']) == category_id:
                category = entry
                break

        if not category:
            raise Http404('Category does not exist')

        cache_key = f'alibaba_ranked_products_{category_id}_{page}'
        if search_query:
            cache_key = f'{cache_key}_{search_query}'

        ranked_products = {}
        if not use_filters:
            ranked_products = cache.get(cache_key, {})
        if search_query and not ranked_products:
            api_url = 'https://dropshipping.alibaba.com/saas/ajax/product/search/query_product'
            params = {
                'category': category['alibaba_category_id'],
                'search_query': search_query,
                'page': page,
                'currency': currency,
                'price_min': safe_int(price_min),
                'price_max': safe_int(price_max),
                'sort': sort,
            }
            ranked_products = get_search(api_url, **params)
            cache.set(cache_key, ranked_products, timeout=600)

        if not ranked_products:
            api_url = f'dropshipping-api/ranked-products?include_nontop=true&category_ids[]={category_id}&page={page}' \
                      f'&price_from={price_min}&price_to={price_max}'
            ranked_products = requests.get(
                settings.INSIDER_REPORT_HOST + api_url,
                verify=False
            ).json()
            if sort.startswith('-'):
                ranked_products['results'] = sorted(ranked_products['results'], key=lambda x: x['total_quantities'], reverse=True)
            else:
                ranked_products['results'] = sorted(ranked_products['results'], key=lambda x: x['total_quantities'])
            cache.set(cache_key, ranked_products, timeout=600)

        if account.user == self.request.user:
            for product in ranked_products['results']:
                product['url'] = f'{product["url"]}?ecology_token={account.ecology_token}'

        store_data = get_store_data(self.request.user)

        paginator = {
            'show': True if len(ranked_products['results']) >= 20 else False,
            'current_page': page,
            'next_page': page + 1,
            'previous_page': page - 1,
        }

        context.update({
            'category': category,
            'categories': ranked_categories,
            'products': ranked_products,
            'total_results': ranked_products['count'],
            'store_data': store_data,
            'paginator': paginator,
            'search_query': search_query,
        })

        return context


@method_decorator(login_required, name='dispatch')
class ProductsRedirectView(RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        try:
            token = self.request.user.models_user.alibaba.first().get_ecology_token()
        except:
            messages.error(self.request, "Your Dropified account is not connected to Alibaba")
            return f"{reverse('settings')}#alibaba-settings"

        params = (
            # ('wx_screen_direc', 'portrait'),
            # ('wx_navbar_transparent', 'true'),
            # ('path', '/p/dt0c706ur/index.html'),
            ('ecology_token', token),
        )
        return f"https://dropshipping.alibaba.com?{urlencode(params)}"
