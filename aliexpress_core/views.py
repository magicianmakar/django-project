import json
import os
import random
import requests

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.views.generic.base import RedirectView

from shopified_core import permissions
from shopified_core.utils import app_link, external_link, safe_int

from .models import AliexpressAccount, AliexpressCategory
from .settings import API_KEY, API_SECRET
from .utils import get_aliexpress_account, get_store_data


class AuthorizeView(RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        redirect_url = app_link(reverse('aliexpress:aliexpress.token'))
        if settings.DEBUG:
            # Aliexpress doesn't redirect to local links for some reason
            redirect_url = redirect_url.replace('dev.', 'app.')

        return external_link(
            url='https://oauth.aliexpress.com/authorize',
            response_type='code',
            client_id=API_KEY,
            redirect_uri=redirect_url,
            state=get_random_string(32),
            view='web',
            sp='ae'
        )


class TokenView(RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        res = requests.post('https://oauth.aliexpress.com/token', data={
            'code': self.request.GET['code'],
            'grant_type': 'authorization_code',
            'client_id': API_KEY,
            'client_secret': API_SECRET,
        })

        if res.ok:
            account, created = AliexpressAccount.objects.update_or_create(
                user=self.request.user.models_user,
                aliexpress_user_id=res.json().get('user_id'),
                aliexpress_username=res.json().get('user_nick'),
                defaults={
                    'access_token': res.json().get('access_token'),
                    'data': res.text
                }
            )

            op = 'created' if created else 'updated'
            messages.success(self.request, f"Your AliExpress account ({account.aliexpress_username}) was successfully {op}")

            return '/settings#aliexpress-settings'


class Products(TemplateView):
    template_name = 'aliexpress/products.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('find_products.view'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        error = ''
        search_query = self.request.GET.get('q', '')
        page = safe_int(self.request.GET.get('page', 1))
        use_filters = self.request.GET.get('f', None)
        sort = self.request.GET.get('sort', '-order_count')
        price_min = safe_int(self.request.GET.get('price_min', None))
        price_max = safe_int(self.request.GET.get('price_max', None))
        upsell = not self.request.user.can('find_products.use')

        categories = AliexpressCategory.parent_ctaegories()
        if upsell:
            dest_file = os.path.join('aliexpress_core/tests/mock_products.json')
            with open(dest_file, 'r') as read_file:
                products_list = json.load(read_file)
                random.shuffle(products_list),

            context.update({
                'upsell': upsell,
                'categories': categories,
                'products': products_list,
                'total_results': f'{random.randint(65000, 75000)}',
                'paginator': {'show': False},
            })

            return context

        aliexpress_account = get_aliexpress_account(user=self.request.user)

        params = {
            'user': self.request.user,
            'page': page,
            'currency': self.request.GET.get('currency', 'USD'),
            'sort': sort,
            'use_cache': False if use_filters else True,
        }

        if search_query:
            params['keywords'] = search_query
            params['price_min'] = price_min
            params['price_max'] = price_max
            total_results, products_list = aliexpress_account.get_affiliate_products(**params)
        else:
            total_results, products_list = aliexpress_account.get_ds_recommended_products(**params)

        if sort.startswith('-'):
            products_list = sorted(products_list, key=lambda x: x[sort.strip('-')], reverse=True)
        else:
            products_list = sorted(products_list, key=lambda x: x[sort])

        store_data = get_store_data(self.request.user)

        if not isinstance(products_list, list) and products_list.get('error', None):
            error = products_list['error']
            products_list = []

        paginator = {
            'show': True if len(products_list) >= 20 else False,
            'current_page': page,
            'next_page': page + 1,
            'previous_page': page - 1,
        }

        context.update({
            'categories': categories,
            'products': products_list,
            'total_results': total_results,
            'store_data': store_data,
            'paginator': paginator,
            'search_query': search_query,
            'error': error,
        })

        return context


class CategoryProducts(TemplateView):
    template_name = 'aliexpress/category_products.html'

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
        error = ''
        search_query = self.request.GET.get('q', '')
        page = safe_int(self.request.GET.get('page', 1))
        use_filters = self.request.GET.get('f', None)
        sort = self.request.GET.get('sort', '-order_count')
        price_min = safe_int(self.request.GET.get('price_min', None))
        price_max = safe_int(self.request.GET.get('price_max', None))

        category_id = kwargs.get('category_id')
        category = get_object_or_404(AliexpressCategory, pk=category_id)

        aliexpress_account = get_aliexpress_account(user=self.request.user)

        params = {
            'user': self.request.user,
            'page': page,
            'category_id': category.aliexpress_id,
            'currency': self.request.GET.get('currency', 'USD'),
            'sort': sort,
            'use_cache': False if use_filters else True,
        }

        if search_query:
            params['keywords'] = search_query
            params['price_min'] = price_min
            params['price_max'] = price_max
            total_results, products_list = aliexpress_account.get_affiliate_products(**params)
        else:
            total_results, products_list = aliexpress_account.get_ds_recommended_products(**params)

        if sort.startswith('-'):
            products_list = sorted(products_list, key=lambda x: x[sort.strip('-')], reverse=True)
        else:
            products_list = sorted(products_list, key=lambda x: x[sort])

        store_data = get_store_data(self.request.user)

        if not isinstance(products_list, list) and products_list.get('error', None):
            error = products_list['error']
            products_list = []

        paginator = {
            'show': True if len(products_list) >= 20 else False,
            'current_page': page,
            'next_page': page + 1,
            'previous_page': page - 1,
        }

        context.update({
            'category': category,
            'categories': AliexpressCategory.parent_ctaegories(),
            'products': products_list,
            'total_results': total_results,
            'store_data': store_data,
            'paginator': paginator,
            'search_query': search_query,
            'error': error,
        })

        return context
