import arrow
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils import timezone

from leadgalaxy import utils
from .utils import (
    retrieve_current_profits,
    calculate_shopify_profit,
    retrieve_facebook_insights,
)
from .models import (
    FacebookAccount,
    ShopifyProfit,
)


@login_required
def index(request):
    if not request.user.can('profit_dashboard.use'):
        raise PermissionDenied()

    start = request.GET.get('start')
    end = request.GET.get('end')
    limit = utils.safeInt(request.GET.get('limit'), 10)
    no_limit = request.GET.get('nolimit', '0') == '1'
    current_page = int(request.GET.get('page', '1'))

    profits = []
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

    if no_limit:
        limit = None

    running_calculation = calculate_shopify_profit(request.user.pk, store.id, start, end)
    profits, max_results, pages, totals = retrieve_current_profits(
        request.user.pk,
        store.id,
        start,
        end,
        current_page,
        limit
    )

    accounts = FacebookAccount.objects.filter(access__user=request.user)

    return render(request, 'profit_dashboard/index.html', {
        'page': 'profit_dashboard', 'profits': profits, 'store': store,
        'start': start.strftime('%m/%d/%Y'), 'end': end.strftime('%m/%d/%Y'),
        'current_page': current_page, 'max_results': max_results, 'pages': pages,
        'limit': limit, 'totals': totals, 'user': request.user, 'accounts': accounts,
        'running_calculation': running_calculation
    })


@login_required
def facebook_insights(request):
    if request.method == 'POST':
        access_token = request.POST.get('access_token')
        store = utils.get_store_from_request(request)
        retrieve_facebook_insights(request.user.pk, store.id, access_token)

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
    filter_end = request.GET.get('filter_end')
    filter_start = request.GET.get('filter_start')
    limit = None
    current_page = 1

    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Profits Dashboard.')
        return HttpResponseRedirect('/')

    tz = timezone.localtime(timezone.now()).strftime(' %z')
    end = arrow.get(end + tz, r'MM/DD/YYYY Z').datetime
    start = arrow.get(start + tz, r'MM/DD/YYYY Z').datetime
    filter_end = arrow.get(filter_end + tz, r'MM/DD/YYYY Z').datetime
    filter_start = arrow.get(filter_start + tz, r'MM/DD/YYYY Z').datetime

    profits, max_results, pages, totals = retrieve_current_profits(
        request.user.pk,
        store.id,
        start,
        end,
        current_page,
        limit,
        filter_date=[filter_start, filter_end]
    )

    return JsonResponse({'profits': profits, 'totals': totals})
