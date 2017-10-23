import arrow
import simplejson as json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils import timezone

from facebookads.api import FacebookAdsApi
from facebookads.adobjects.user import User as FBUser
from facebookads.adobjects.adaccount import AdAccount

from leadgalaxy import utils
from shopified_core.paginators import SimplePaginator
from .utils import (
    get_profits,
    calculate_profits,
)
from .models import (
    FacebookAccess,
    FacebookAccount,
    OtherCost,
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

    profits, totals = get_profits(request.user.pk, store.id, start, end)

    profits_json = json.dumps(profits[::-1])
    profits_per_page = len(profits) + 1 if limit == 0 else limit
    paginator = SimplePaginator(profits, profits_per_page)
    page = min(max(1, current_page), paginator.num_pages)
    page = paginator.page(page)
    profits = calculate_profits(page.object_list)

    accounts = FacebookAccount.objects.filter(access__user=request.user)
    need_setup = not FacebookAccess.objects.filter(user=request.user, store=store).exists()

    return render(request, 'profit_dashboard/index.html', {
        'page': 'profit_dashboard',
        'profits': profits,
        'store': store,
        'start': start.strftime('%m/%d/%Y'),
        'end': end.strftime('%m/%d/%Y'),
        'current_page': page,
        'paginator': paginator,
        'limit': limit,
        'totals': totals,
        'user': request.user,
        'accounts': accounts,
        'need_setup': need_setup,
        'profits_json': profits_json
    })


@login_required
def facebook_insights(request):
    if request.method == 'POST':
        access_token = request.POST.get('fb_access_token')
        store = utils.get_store_from_request(request)

        account_ids = request.POST.get('accounts').split(',') if request.POST.get('accounts') else []
        campaigns = request.POST.get('campaigns').split(',') if request.POST.get('campaigns') else []

        fetch_facebook_insights.delay(request.user.pk, store.id, access_token, account_ids, campaigns)

        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Non-handled endpoint'}, status=405)


@login_required
def facebook_accounts(request):
    access_token = request.GET.get('fb_access_token')

    api = FacebookAdsApi.init(
        settings.FACEBOOK_APP_ID,
        settings.FACEBOOK_APP_SECRET,
        access_token
    )

    user = FBUser(fbid='me', api=api)
    accounts = user.get_ad_accounts(fields=[AdAccount.Field.name])

    return JsonResponse({
        'accounts': [{'name': i['name'], 'id': i['id']} for i in accounts]
    })


@login_required
def facebook_campaign(request):
    access_token = request.GET.get('fb_access_token')
    account_id = request.GET.get('account_id')

    api = FacebookAdsApi.init(
        settings.FACEBOOK_APP_ID,
        settings.FACEBOOK_APP_SECRET,
        access_token
    )

    user = FBUser(fbid='me', api=api)
    for account in user.get_ad_accounts(fields=[AdAccount.Field.name]):
        if account['id'] == account_id:
            return JsonResponse({
                'campaigns': [{
                    'id': i['id'],
                    'name': i['name'],
                    'status': i['status'].title(),
                    'created_time': arrow.get(i['created_time']).humanize()
                } for i in account.get_campaigns(fields=['name', 'status', 'created_time'])]
            })

    return JsonResponse({'error': 'Ad Account Not found'})


@login_required
def save_other_costs(request):
    amount = float(request.POST.get('amount', '0'))
    date = arrow.get(request.POST.get('date'), r'MMDDYYYY').date()

    store = utils.get_store_from_request(request)
    if not store:
        return JsonResponse({
            'error': 'Please add at least one store before using the Profits Dashboard.'
        }, status=500)

    OtherCost.objects.update_or_create(store=store, date=date, defaults={'amount': amount})

    return JsonResponse({'status': 'ok'})
