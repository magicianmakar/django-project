import arrow
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import render

from lib.exceptions import capture_exception

from shopified_core.mocks import get_mocked_profits
from shopified_core.utils import safe_int
from shopified_core.paginators import SimplePaginator

from . import utils
from . import models
from . import tasks


class ProfitDashboardMixin():
    template_name = 'profits/index.html'
    model = models.ProfitSync

    store_type = None
    store_model = None

    def get_store(self):
        if not hasattr(self, 'store'):
            self.store = utils.get_store_from_request(self.request, self.store_type)
            self.store_content_type = ContentType.objects.get_for_model(self.store)

            sync, created = models.ProfitSync.objects.get_or_create(
                store_content_type=self.store_content_type,
                store_object_id=self.store.id
            )

            if created or sync.last_sync < arrow.get().shift(days=-1).datetime:  # Sync daily
                if self.store_type == 'gkart':
                    tasks.sync_gkart_store_profits.delay(sync.id, self.store.id)
                elif self.store_type == 'bigcommerce':
                    tasks.sync_bigcommerce_store_profits.delay(sync.id, self.store.id)
                elif self.store_type == 'woo':
                    tasks.sync_woocommerce_store_profits.delay(sync.id, self.store.id)

            if created or sync.last_sync < arrow.get().shift(hours=-1).datetime:  # Sync hourly
                if self.store_type == 'chq':
                    tasks.sync_commercehq_store_profits.delay(sync.id, self.store.id)

        return self.store

    def dispatch(self, request, *args, **kwargs):
        if not self.store_type:
            raise NotImplementedError('Store Type')

        store = self.get_store()
        if not store:
            messages.warning(request, 'Please add at least one store before using the Profit Dashboard page')
            return HttpResponseRedirect('/')

        if not request.user.can('profit_dashboard.use'):
            if not request.user.is_subuser:
                return render(request, 'profits/index.html', get_mocked_profits(store))
            else:
                raise PermissionDenied()

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        store = self.get_store()

        context = {
            'page': 'profit_dashboard',
            'base_template': self.base_template,
            'store': store,
            'store_type': self.store_type,
            'stores': utils.get_stores(self.request.user, self.store_type),
            'user_facebook_permission': settings.FACEBOOK_APP_ID,
            'initial_date': models.INITIAL_DATE.isoformat(),
            'show_facebook_connection': self.request.user.get_config('_show_facebook_connection', 'true') == 'true',
        }

        # Get correct timezone to properly sum order amounts
        user_timezone = self.request.session.get('django_timezone', '')
        if not user_timezone and self.request.user.profile.timezone:
            user_timezone = self.request.user.profile.timezone
            self.request.session['django_timezone'] = user_timezone

        try:
            start, end = utils.get_date_range(self.request, user_timezone)
            limit = safe_int(self.request.GET.get('limit'), 31)
            current_page = safe_int(self.request.GET.get('page'), 1)

            profits, totals, details = utils.get_profits(store, self.store_type, start, end, user_timezone)
            profit_details, details_paginator = details

            profits_json = json.dumps(profits[::-1])
            profits_per_page = len(profits) + 1 if limit == 0 else limit
            paginator = SimplePaginator(profits, profits_per_page)
            page = min(max(1, current_page), paginator.num_pages)
            page = paginator.page(page)
            profits = utils.calculate_profits(page.object_list)

            accounts = models.FacebookAccount.objects.filter(
                access__store_content_type=self.store_content_type,
                access__store_object_id=store.id
            )
            need_setup = not models.FacebookAccess.objects.filter(
                store_content_type=self.store_content_type,
                store_object_id=store.id
            ).exists()

            context.update({
                'profits': profits,
                'start': start.strftime('%m/%d/%Y'),
                'end': end.strftime('%m/%d/%Y'),
                'current_page': page,
                'paginator': paginator,
                'limit': limit,
                'totals': totals,
                'accounts': accounts,
                'need_setup': need_setup,
                'profits_json': profits_json,
                'profit_details': profit_details,
                'details_paginator': details_paginator,
            })

        except:
            context['api_error'] = 'API Error'
            capture_exception()

        return context
