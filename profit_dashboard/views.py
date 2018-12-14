import arrow
import requests
import simplejson as json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string

from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy import utils
from shopified_core.paginators import SimplePaginator
from shopify_orders.utils import is_store_synced
from .utils import (
    get_profits,
    calculate_profits,
    get_profit_details,
    get_date_range,
)
from .models import (
    INITIAL_DATE,
    CONFIG_CHOICES,
    FacebookAccess,
    FacebookAccount,
    OtherCost,
)
from .tasks import fetch_facebook_insights


@login_required
def index(request):
    if not request.user.can('profit_dashboard.use'):
        if not request.user.is_subuser:
            return render(request, 'profit_dashboard/upsell.html', {'page': 'profit_dashboard'})
        else:
            raise PermissionDenied()

    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Profits Dashboard')
        return HttpResponseRedirect('/')

    context = {
        'page': 'profit_dashboard',
        'store': store,
        'user_facebook_permission': settings.FACEBOOK_APP_ID,
        'initial_date': INITIAL_DATE.isoformat(),
        'show_facebook_connection': request.user.get_config('_show_facebook_connection', 'true') == 'true',
    }

    if not is_store_synced(store):
        context['api_error'] = 'Your orders are not synced yet'
        return render(request, 'profit_dashboard/index.html', context)

    # Get correct timezone to properly sum order amounts
    user_timezone = request.session.get('django_timezone', '')
    if not user_timezone:
        user_timezone = store.get_info['iana_timezone']
        request.session['django_timezone'] = user_timezone

        # Save timezone to profile
        if not request.user.profile.timezone:
            request.user.profile.timezone = user_timezone
            request.user.profile.save()

    try:
        start, end = get_date_range(request, user_timezone)
        limit = utils.safeInt(request.GET.get('limit'), 31)
        current_page = utils.safeInt(request.GET.get('page'), 1)

        profits, totals, details = get_profits(store, start, end, user_timezone)
        profit_details, details_paginator = details

        profits_json = json.dumps(profits[::-1])
        profits_per_page = len(profits) + 1 if limit == 0 else limit
        paginator = SimplePaginator(profits, profits_per_page)
        page = min(max(1, current_page), paginator.num_pages)
        page = paginator.page(page)
        profits = calculate_profits(page.object_list)

        accounts = FacebookAccount.objects.filter(access__store=store)
        need_setup = not FacebookAccess.objects.filter(store=store).exists()

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

    except json.JSONDecodeError:
        context['api_error'] = 'Unexpected response content'
        raven_client.captureException()

    except requests.exceptions.ConnectTimeout:
        context['api_error'] = 'Connection Timeout'
        raven_client.captureException()

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            context['api_error'] = 'API Rate Limit'
        elif e.response.status_code == 404:
            context['api_error'] = 'Store Not Found'
        elif e.response.status_code == 402:
            context['api_error'] = 'Your Shopify Store is not on a paid plan'
        elif e.response.status_code == 401:
            context['api_error'] = 'Access Token Error'
        else:
            context['api_error'] = 'Unknown Error {}'.format(e.response.status_code)
            raven_client.captureException()
    except:
        context['api_error'] = 'Shopify API Error'
        raven_client.captureException()

    return render(request, 'profit_dashboard/index.html', context)


@login_required
def facebook_insights(request):
    """ Save campaigns to account(if selected) and fetch insights
    """
    if request.method == 'POST':
        facebook_access_id = request.POST.get('facebook_access_id')
        store = utils.get_store_from_request(request)

        # Update (if found) facebook account sync meta data
        account_id = request.POST.get('account_id')
        campaigns = request.POST.get('campaigns')
        config = request.POST.get('config')
        FacebookAccount.objects.filter(
            access_id=facebook_access_id,
            access__store=store,
            account_id=account_id
        ).update(campaigns=campaigns, config=config)

        # Sync specific user or all users
        facebook_access_list = FacebookAccess.objects.filter(store=store)
        if facebook_access_id:
            # FacebookAccess queryset might return empty
            facebook_access_list = facebook_access_list.filter(id=facebook_access_id)

            # Force renewal of FacebookAccess.access_token in case its expired or empty
            access_token = request.POST.get('fb_access_token')
            expires_in = utils.safeInt(request.POST.get('fb_expires_in'))
            facebook_access = facebook_access_list.first()
            if access_token and facebook_access:
                facebook_access.get_or_update_token(access_token, expires_in)

        # Sync insights with found FacebookAccess
        fetch_facebook_insights.delay(
            store.id,
            [f.pk for f in facebook_access_list]
        )

        return JsonResponse({'status': 'ok'})

    return JsonResponse({'error': 'Non-handled endpoint'}, status=405)


@login_required
def facebook_accounts(request):
    """ Save access token and return accounts
    """
    store = utils.get_store_from_request(request)
    access_token = request.GET.get('fb_access_token')
    expires_in = utils.safeInt(request.GET.get('fb_expires_in'))
    facebook_user_id = request.GET.get('fb_user_id')

    # Sometimes facebook doesn't reload the access_token and it comes empty
    if not access_token:
        # Only use previous access if current user created and there is only one
        facebook_access = FacebookAccess.objects.filter(user_id=request.user, store=store)
        if facebook_access.count() == 1:
            facebook_access = facebook_access.first()
            access_token = facebook_access.access_token
            facebook_user_id = facebook_access.facebook_user_id
        else:
            return JsonResponse({'error': 'Facebook token not received, please refresh your page and try again'}, status=404)

    try:
        facebook_access = FacebookAccess.objects.get(
            user_id=request.user.models_user.id,
            store=store,
            facebook_user_id=facebook_user_id
        )

    except FacebookAccess.DoesNotExist:
        facebook_access = FacebookAccess.objects.create(
            user_id=request.user.models_user.id,
            store=store,
            facebook_user_id=facebook_user_id,
            access_token=access_token,
            expires_in=arrow.get().replace(seconds=expires_in).datetime
        )

    except FacebookAccess.MultipleObjectsReturned:
        facebook_access = FacebookAccess.objects.filter(
            user_id=request.user.models_user.id,
            store=store,
            facebook_user_id=facebook_user_id
        ).first()

    try:
        facebook_access.get_or_update_token(access_token, expires_in)
        accounts = facebook_access.get_api_accounts()
    except:
        raven_client.captureException()
        return JsonResponse({'error': 'User token error'}, status=404)

    return JsonResponse({
        'accounts': [{'name': i['name'], 'id': i['id']} for i in accounts],
        'facebook_access_id': facebook_access.pk
    })


@login_required
def facebook_campaign(request):
    """ Save account and return campaigns
    """
    store = utils.get_store_from_request(request)
    facebook_access_id = request.GET.get('facebook_access_id')
    try:
        facebook_access = FacebookAccess.objects.get(
            id=facebook_access_id,
            store_id=store.id,
            user_id=request.user.models_user.id
        )
    except:
        return JsonResponse({'error': 'Facebook Access permission denied'}, status=403)

    account_id = request.GET.get('account_id')
    account_name = request.GET.get('account_name')

    # Save selected account_id
    account_ids = facebook_access.account_ids and facebook_access.account_ids.split(',') or []
    if account_id and account_id not in account_ids:
        account_ids.append(account_id)
        facebook_access.account_ids = ','.join(account_ids)
        facebook_access.save()

    # Create with facebook sync starting at profit dashboard's INITIAL_DATE
    facebook_account, created = FacebookAccount.objects.update_or_create(
        store=store,
        access_id=facebook_access.pk,
        account_id=account_id,
        defaults={
            'account_name': account_name,
            'last_sync': INITIAL_DATE.date()
        }
    )

    # Get config options remembering previously synced accounts
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

    # Returns campaigns remembering previously synced accounts
    saved_campaigns = facebook_account.campaigns.split(',')
    try:
        return JsonResponse({
            'campaigns': [{
                'id': i['id'],
                'name': i['name'],
                'status': i['status'].title(),
                'created_time': arrow.get(i['created_time']).humanize(),
                'checked': 'checked' if i['id'] in saved_campaigns else ''
            } for i in facebook_account.get_api_campaigns()],
            'config_options': config_options
        })
    except:
        raven_client.captureException()
        return JsonResponse({'error': 'Ad Account Not found'}, status=404)


@login_required
def save_other_costs(request):
    amount = float(request.POST.get('amount', '0'))
    date = arrow.get(request.POST.get('date'), r'MMDDYYYY').date()

    store = utils.get_store_from_request(request)
    if not store:
        return JsonResponse({
            'error': 'Please add at least one store before using the Profits Dashboard.'
        }, status=500)

    while True:
        try:
            OtherCost.objects.update_or_create(
                store=store,
                date=date,
                defaults={
                    'amount': amount
                }
            )

            break

        except OtherCost.MultipleObjectsReturned:
            OtherCost.objects.filter(store=store, date=date).delete()

    return JsonResponse({'status': 'ok'})


@login_required
def facebook_remove_account(request):
    if request.method == 'POST':
        store = utils.get_store_from_request(request)
        access = get_object_or_404(FacebookAccess,
                                   user=request.user.models_user,
                                   store=store,
                                   facebook_user_id=request.POST.get('facebook_user_id'))
        account = access.accounts.filter(pk=request.POST.get('id'))

        # Remove account_id from FacebookAccess.account_ids
        account_ids = access.account_ids.split(',')
        current_account_id = account.first().account_id
        account_ids = filter(lambda account_id: account_id != current_account_id, account_ids)
        access.account_ids = ','.join(account_ids)
        access.save()

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

    store_timezone = request.session.get('django_timezone', '')
    start, end = get_date_range(request, store_timezone)
    limit = utils.safeInt(request.GET.get('limit'), 20)
    current_page = utils.safeInt(request.GET.get('page'), 1)

    details, paginator = get_profit_details(store,
                                            (start, end),
                                            limit=limit,
                                            page=current_page,
                                            store_timezone=store_timezone)

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


@login_required
def facebook_remove(request):
    if request.method == 'POST':
        store = utils.get_store_from_request(request)
        access = get_object_or_404(FacebookAccess,
                                   user=request.user.models_user,
                                   store=store,
                                   facebook_user_id=request.POST.get('facebook_user_id'))

        access.access_token = ''
        access.expires_in = None
        access.save()

        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Non-handled endpoint'}, status=405)
