import arrow
import simplejson as json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string

from facebookads.adobjects.user import User as FBUser
from facebookads.adobjects.adaccount import AdAccount

from leadgalaxy import utils
from shopified_core.paginators import SimplePaginator
from shopify_orders.utils import is_store_synced
from .utils import (
    INITIAL_DATE,
    get_profits,
    calculate_profits,
    get_facebook_api,
    get_profit_details,
    get_date_range,
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

    start, end = get_date_range(request)
    limit = utils.safeInt(request.GET.get('limit'), 31)
    current_page = utils.safeInt(request.GET.get('page'), 1)

    profits, totals, details = get_profits(request.user.pk, store, start, end, request.session['django_timezone'])
    profit_details, details_paginator = details

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
        'profit_details': profit_details,
        'details_paginator': details_paginator,
        'user_facebook_permission': settings.FACEBOOK_APP_ID,
        'initial_date': INITIAL_DATE.format('MM/DD/YYYY'),
    })


@login_required
def facebook_insights(request):
    """ Save campaigns to account(if selected) and fetch insights
    """
    if request.method == 'POST':
        access_token = request.POST.get('fb_access_token')
        expires_in = utils.safeInt(request.GET.get('fb_expires_in'))
        store = utils.get_store_from_request(request)

        # Update facebook account sync meta data
        account_id = request.POST.get('account_id')
        campaigns = request.POST.get('campaigns')
        config = request.POST.get('config')
        FacebookAccount.objects.filter(
            access__user=request.user,
            access__store=store,
            account_id=account_id
        ).update(campaigns=campaigns, config=config)

        fetch_facebook_insights.delay(request.user.pk, store.id, access_token, expires_in)

        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Non-handled endpoint'}, status=405)


@login_required
def facebook_accounts(request):
    """ Save access token and return accounts
    """
    access_token = request.GET.get('fb_access_token')
    expires_in = utils.safeInt(request.GET.get('fb_expires_in'))
    store = utils.get_store_from_request(request)
    facebook_access, created = FacebookAccess.objects.get_or_create(user=request.user, store=store, defaults={
        'access_token': access_token,
        'expires_in': arrow.get().replace(seconds=expires_in).datetime
    })
    access_token = facebook_access.get_or_update_token(access_token, expires_in)

    api = get_facebook_api(access_token)
    user = FBUser(fbid='me', api=api)
    accounts = user.get_ad_accounts(fields=[AdAccount.Field.name])

    return JsonResponse({
        'accounts': [{'name': i['name'], 'id': i['id']} for i in accounts]
    })


@login_required
def facebook_campaign(request):
    """ Save account and return campaigns
    """
    store = utils.get_store_from_request(request)
    facebook_access = FacebookAccess.objects.get(user=request.user, store=store)
    access_token = facebook_access.get_or_update_token()
    account_id = request.GET.get('account_id')
    account_name = request.GET.get('account_name')

    # Save selected account_id
    account_ids = facebook_access.account_ids and facebook_access.account_ids.split(',') or []
    if account_id not in account_ids:
        account_ids.append(account_id)
        facebook_access.account_ids = ','.join(account_ids)
        facebook_access.save()
        facebook_access.refresh_from_db()

    # Create with facebook sync starting at profit dashboard's INITIAL_DATE
    facebook_account, created = FacebookAccount.objects.update_or_create(
        store=store,
        access=facebook_access,
        account_id=account_id,
        defaults={
            'account_name': account_name,
            'last_sync': INITIAL_DATE.date()
        }
    )

    # Get config options minding previous synced accounts
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

    # Returns campaigns minding previous synced accounts
    saved_campaigns = facebook_account.campaigns.split(',')
    api = get_facebook_api(access_token)
    user = FBUser(fbid='me', api=api)
    for account in user.get_ad_accounts(fields=[AdAccount.Field.name]):
        if account['id'] == account_id:
            return JsonResponse({
                'campaigns': [{
                    'id': i['id'],
                    'name': i['name'],
                    'status': i['status'].title(),
                    'created_time': arrow.get(i['created_time']).humanize(),
                    'checked': 'checked' if i['id'] in saved_campaigns else ''
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

    other_costs, created = OtherCost.objects.get_or_create(store=store, date=date, defaults={'amount': amount})
    if not created:
        other_costs.amount = amount
        other_costs.save()

    return JsonResponse({'status': 'ok'})


@login_required
def facebook_remove_account(request):
    if request.method == 'POST':
        store = utils.get_store_from_request(request)

        access = get_object_or_404(FacebookAccess, user=request.user, store=store)
        # Remove account_id from FacebookAccess.account_ids
        acount_ids = access.account_ids.split(',')
        acount_ids = filter(lambda account_id: account_id != account.account_id, acount_ids)
        access.account_ids = acount_ids.join(',')

        account = access.accounts.filter(pk=request.POST.get('id'))
        account.delete()

        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Non-handled endpoint'}, status=405)


@login_required
def profit_details(request):
    store = utils.get_store_from_request(request)
    if not store:
        return JsonResponse({
            'error': 'Please add at least one store before using the Profits Dashboard.'
        }, status=500)

    start, end = get_date_range(request)
    limit = utils.safeInt(request.GET.get('limit'), 20)
    current_page = utils.safeInt(request.GET.get('page'), 1)

    details, paginator = get_profit_details(store,
                                            (start, end),
                                            limit=limit,
                                            page=current_page,
                                            store_timezone=request.session['django_timezone'])

    pagination = render_to_string('partial/paginator.html', {
        'request': request,
        'paginator': paginator,
        'current_page': details
    })

    return JsonResponse({
        'status': 'ok',
        'details': details.object_list,
        'pagination': pagination
    })
