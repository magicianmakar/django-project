import arrow
import simplejson as json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone

from facebookads.adobjects.user import User as FBUser
from facebookads.adobjects.adaccount import AdAccount

from leadgalaxy import utils
from shopified_core.paginators import SimplePaginator
from shopify_orders.utils import is_store_synced
from .utils import (
    get_profits,
    calculate_profits,
    get_facebook_api,
)
from .models import (
    CONFIG_CHOICES,
    FacebookAccess,
    FacebookAccount,
    OtherCost,
)
from .tasks import fetch_facebook_insights


@login_required
def index(request):
    if not request.user.can('profit_dashboard.use'):
        raise PermissionDenied()

    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Profits Dashboard')
        return HttpResponseRedirect('/')

    if not is_store_synced(store):
        messages.warning(request, 'Your orders are not synced yet')
        return HttpResponseRedirect('/')

    start = request.GET.get('start')
    end = request.GET.get('end')
    limit = utils.safeInt(request.GET.get('limit'), 0)
    current_page = utils.safeInt(request.GET.get('page'), 1)

    tz = timezone.localtime(timezone.now()).strftime(' %z')
    if end is None:
        end = arrow.now()
    else:
        end = arrow.get(end + tz, r'MM/DD/YYYY Z')

    if start is None:
        start = arrow.now().replace(days=-30)
    else:
        start = arrow.get(start + tz, r'MM/DD/YYYY Z')

    end = end.to(request.session['django_timezone']).datetime
    start = start.to(request.session['django_timezone']).datetime

    profits, totals = get_profits(request.user.pk, store, start, end, request.session['django_timezone'])

    profits_json = json.dumps(profits[::-1])
    profits_per_page = len(profits) + 1 if limit == 0 else limit
    paginator = SimplePaginator(profits, profits_per_page)
    page = min(max(1, current_page), paginator.num_pages)
    page = paginator.page(page)
    profits = calculate_profits(page.object_list)

    accounts = FacebookAccount.objects.filter(access__store=store, access__user=request.user)
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
        'profits_json': profits_json,
        'user_facebook_permission': request.user.can('profit_dashboard_facebook.use')
    })


@login_required
def facebook_insights(request):
    if request.method == 'POST':
        access_token = request.POST.get('fb_access_token')
        store = utils.get_store_from_request(request)

        account_ids = request.POST.get('accounts').split(',') if request.POST.get('accounts') else []
        campaigns = request.POST.get('campaigns').split(',') if request.POST.get('campaigns') else []
        config = request.POST.get('config')

        fetch_facebook_insights.delay(request.user.pk, store.id, access_token, account_ids, campaigns, config)

        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Non-handled endpoint'}, status=405)


@login_required
def facebook_accounts(request):
    access_token = request.GET.get('fb_access_token')

    api = get_facebook_api(access_token)

    user = FBUser(fbid='me', api=api)
    accounts = user.get_ad_accounts(fields=[AdAccount.Field.name])

    return JsonResponse({
        'accounts': [{'name': i['name'], 'id': i['id']} for i in accounts]
    })


@login_required
def facebook_campaign(request):
    access_token = request.GET.get('fb_access_token')
    account_id = request.GET.get('account_id')

    api = get_facebook_api(access_token)

    store = utils.get_store_from_request(request)
    access, created = FacebookAccess.objects.get_or_create(
        user=request.user,
        store=store,
        defaults={'access_token': access_token}
    )
    saved_campaigns = access.campaigns.split(',')

    facebook_account = FacebookAccount.objects.filter(
        account_id=account_id,
        access=access,
        store=store,
    )
    updated = None
    if facebook_account.exists():
        facebook_account = facebook_account.first()
        if facebook_account.config == 'include_and_new':
            updated = arrow.get(facebook_account.last_sync)

    config_options = []
    for option in CONFIG_CHOICES:
        selected = ''
        if facebook_account and facebook_account.config == option[0]:
            selected = 'selected'

        config_options.append({
            'key': option[0],
            'value': option[1],
            'selected': selected
        })

    user = FBUser(fbid='me', api=api)
    for account in user.get_ad_accounts(fields=[AdAccount.Field.name]):
        if account['id'] == account_id:
            return JsonResponse({
                'campaigns': [{
                    'id': i['id'],
                    'name': i['name'],
                    'status': i['status'].title(),
                    'created_time': arrow.get(i['created_time']).humanize(),
                    'checked': 'checked' if i['id'] in saved_campaigns or
                    (updated is not None and arrow.get(i['created_time']) > updated)
                    else ''
                } for i in account.get_campaigns(fields=['name', 'status', 'created_time'])],
                'config_options': config_options
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


@login_required
def facebook_remove_account(request):
    if request.method == 'POST':
        store = utils.get_store_from_request(request)
        access = get_object_or_404(FacebookAccess, user=request.user, store=store)

        account = access.accounts.filter(pk=request.POST.get('id'))
        account.delete()

        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Non-handled endpoint'}, status=405)
