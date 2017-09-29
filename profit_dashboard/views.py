import arrow
import simplejson as json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils import timezone

from leadgalaxy import utils
from shopified_core.paginators import SimplePaginator
from .utils import (
    retrieve_current_profits,
    calculate_shopify_profit,
)
from .models import (
    FacebookAccount,
    ShopifyProfit,
)
from .tasks import fetch_facebook_insights


@login_required
def index(request):
    if not request.user.can('profit_dashboard.use'):
        raise PermissionDenied()

    start = request.GET.get('start')
    end = request.GET.get('end')
    limit = utils.safeInt(request.GET.get('limit'), 10)
    current_page = utils.safeInt(request.GET.get('page'), 1)

    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Profits Dashboard.')
        return HttpResponseRedirect('/')

    tz = timezone.localtime(timezone.now()).strftime(' %z')
    if end is None:
        end = arrow.now().span('month')[1].datetime
    else:
        end = arrow.get(end + tz, r'MM/DD/YYYY Z').datetime

    if start is None:
        start = end - timedelta(days=end.day - 1)
    else:
        start = arrow.get(start + tz, r'MM/DD/YYYY Z').datetime

    running_calculation = calculate_shopify_profit(store.id, start, end)
    profits, totals = retrieve_current_profits(
        request.user.pk,
        store.id,
        start,
        end
    )

    profits_json = json.dumps(profits[::-1])
    profits_per_page = len(profits) + 1 if limit == 0 else limit
    paginator = SimplePaginator(profits, profits_per_page)
    page = min(max(1, current_page), paginator.num_pages)
    page = paginator.page(page)
    profits = page.object_list

    accounts = FacebookAccount.objects.filter(access__user=request.user)

    return render(request, 'profit_dashboard/index.html', {
        'page': 'profit_dashboard', 'profits': profits, 'store': store,
        'start': start.strftime('%m/%d/%Y'), 'end': end.strftime('%m/%d/%Y'),
        'current_page': page, 'paginator': paginator, 'limit': limit,
        'totals': totals, 'user': request.user, 'accounts': accounts,
        'running_calculation': running_calculation, 'profits_json': profits_json
    })


@login_required
def facebook_insights(request):
    if request.method == 'POST':
        access_token = request.POST.get('access_token')
        store = utils.get_store_from_request(request)
        fetch_facebook_insights.delay(request.user.pk, store.id, access_token)

        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Non-handled endpoint'}, status=405)


@login_required
def save_other_costs(request):
    amount = float(request.POST.get('amount', '0'))
    tz = timezone.localtime(timezone.now()).strftime(' %z')
    date = arrow.get(request.POST.get('date') + tz, r'MMDDYYYY Z').datetime

    store = utils.get_store_from_request(request)
    if not store:
        return JsonResponse({
            'error': 'Please add at least one store before using the Profits Dashboard.'
        }, status=500)

    ShopifyProfit.objects.update_or_create(store=store, date=date, defaults={'other_costs': amount})

    return JsonResponse({'status': 'ok'})


@login_required
def profits(request):
    start = request.GET.get('start')
    end = request.GET.get('end')
    limit = utils.safeInt(request.GET.get('limit'), 10)
    current_page = utils.safeInt(request.GET.get('page'), 1)

    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Profits Dashboard.')
        return HttpResponseRedirect('/')

    tz = timezone.localtime(timezone.now()).strftime(' %z')
    end = arrow.get(end + tz, r'MM/DD/YYYY Z').datetime
    start = arrow.get(start + tz, r'MM/DD/YYYY Z').datetime

    profits, totals = retrieve_current_profits(
        request.user.pk,
        store.id,
        start,
        end
    )

    chart_profits = profits[::-1]
    profits_per_page = len(profits) + 1 if limit == 0 else limit
    paginator = SimplePaginator(profits, profits_per_page)
    page = min(max(1, current_page), paginator.num_pages)
    page = paginator.page(page)
    profits = page.object_list

    return JsonResponse({'profits': profits, 'totals': totals, 'chart_profits': chart_profits})
