import arrow
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.generic import View
from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.utils import safe_int
from shopified_core.mixins import ApiResponseMixin

from . import models
from . import tasks
from . import utils


class ProfitsApi(ApiResponseMixin, View):
    def get_details(self, request, user, data):
        store_type = data.get('store_type')
        store = utils.get_store_from_request(request, store_type)
        user_timezone = request.session.get('django_timezone', '')
        start, end = utils.get_date_range(request, user_timezone)
        limit = safe_int(data.get('limit'), 20)
        current_page = safe_int(data.get('page'), 1)

        details, paginator = utils.get_profit_details(store,
                                                      store_type,
                                                      (start, end),
                                                      limit=limit,
                                                      page=current_page,
                                                      user_timezone=user_timezone)

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

    def post_save_other_costs(self, request, user, data):
        amount = float(data.get('amount', '0'))
        date = arrow.get(data.get('date'), r'MMDDYYYY').date()

        store_type = data.get('store_type')
        store = utils.get_store_from_request(request, store_type)
        store_content_type = ContentType.objects.get_for_model(store)

        while True:
            try:
                models.OtherCost.objects.update_or_create(
                    store_content_type=store_content_type,
                    store_object_id=store.id,
                    date=date,
                    defaults={
                        'amount': amount
                    }
                )

                break

            except models.OtherCost.MultipleObjectsReturned:
                models.OtherCost.objects.filter(
                    store_content_type=store_content_type,
                    store_object_id=store.id,
                    date=date
                ).delete()

        return JsonResponse({'status': 'ok'})

    def post_facebook_insights(self, request, user, data):
        """ Save campaigns to account(if selected) and fetch insights
        """
        facebook_access_id = data.get('facebook_access_id')
        store_type = data.get('store_type')
        store = utils.get_store_from_request(request, store_type)

        # Update (if found) facebook account sync meta data
        account_id = data.get('account_id')
        campaigns = data.get('campaigns')
        config = data.get('config')

        store_content_type = ContentType.objects.get_for_model(store)
        models.FacebookAccount.objects.filter(
            access_id=facebook_access_id,
            account_id=account_id
        ).update(
            campaigns=campaigns,
            config=config,
            last_sync=models.INITIAL_DATE.date()
        )

        # Sync specific user or all users
        facebook_access_list = models.FacebookAccess.objects.filter(
            store_content_type=store_content_type,
            store_object_id=store.id
        )
        if facebook_access_id:
            # FacebookAccess queryset might return empty
            facebook_access_list = facebook_access_list.filter(id=facebook_access_id)

            # Force renewal of FacebookAccess.access_token in case its expired or empty
            access_token = data.get('fb_access_token')
            expires_in = safe_int(data.get('fb_expires_in'))
            facebook_access = facebook_access_list.first()
            if access_token and facebook_access:
                facebook_access.get_or_update_token(access_token, expires_in)

        # Sync insights with found FacebookAccess
        tasks.fetch_facebook_insights.delay(
            store.id,
            store_type,
            [f.pk for f in facebook_access_list]
        )

        return JsonResponse({'status': 'ok'})

    def get_facebook_accounts(self, request, user, data):
        """ Save access token and return accounts
        """
        store_type = data.get('store_type')
        store = utils.get_store_from_request(request, store_type)
        store_content_type = ContentType.objects.get_for_model(store)

        access_token = data.get('fb_access_token')
        expires_in = safe_int(data.get('fb_expires_in'))
        facebook_user_id = data.get('fb_user_id')

        # Sometimes facebook doesn't reload the access_token and it comes empty
        if not access_token:
            # Only use previous access if current user created and there is only one
            facebook_access = models.FacebookAccess.objects.filter(
                user_id=request.user,
                store_content_type=store_content_type,
                store_object_id=store.id
            )
            if facebook_access.count() == 1:
                facebook_access = facebook_access.first()
                access_token = facebook_access.access_token
                facebook_user_id = facebook_access.facebook_user_id
            else:
                return JsonResponse({'error': 'Facebook token not received, please refresh your page and try again'}, status=404)

        try:
            facebook_access = models.FacebookAccess.objects.get(
                user_id=request.user.models_user.id,
                store_content_type=store_content_type,
                store_object_id=store.id,
                facebook_user_id=facebook_user_id
            )

        except models.FacebookAccess.DoesNotExist:
            facebook_access = models.FacebookAccess.objects.create(
                user_id=request.user.models_user.id,
                store_content_type=store_content_type,
                store_object_id=store.id,
                facebook_user_id=facebook_user_id,
                access_token=access_token,
                expires_in=arrow.get().replace(seconds=expires_in).datetime
            )

        except models.FacebookAccess.MultipleObjectsReturned:
            facebook_access = models.FacebookAccess.objects.filter(
                user_id=request.user.models_user.id,
                store_content_type=store_content_type,
                store_object_id=store.id,
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

    def get_facebook_campaigns(self, request, user, data):
        """ Save account and return campaigns
        """
        store_type = data.get('store_type')
        store = utils.get_store_from_request(request, store_type)
        store_content_type = ContentType.objects.get_for_model(store)

        facebook_access_id = data.get('facebook_access_id')
        account_id = data.get('account_id')
        account_name = data.get('account_name')

        try:
            facebook_access = models.FacebookAccess.objects.get(
                id=facebook_access_id,
                store_content_type=store_content_type,
                store_object_id=store.id,
                user_id=request.user.models_user.id
            )
        except:
            return JsonResponse({'error': 'Facebook Access permission denied'}, status=403)

        # Create with facebook sync starting at profit dashboard's INITIAL_DATE
        facebook_account, created = models.FacebookAccount.objects.update_or_create(
            access_id=facebook_access.pk,
            account_id=account_id,
            defaults={
                'account_name': account_name,
                'last_sync': models.INITIAL_DATE.date()
            }
        )

        # Get config options remembering previously synced accounts
        config_options = []
        for option in models.CONFIG_CHOICES:
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

    def post_facebook_remove_account(self, request, user, data):
        store_type = data.get('store_type')
        store = utils.get_store_from_request(request, store_type)
        store_content_type = ContentType.objects.get_for_model(store)
        access = get_object_or_404(models.FacebookAccess,
                                   user=request.user.models_user,
                                   store_content_type=store_content_type,
                                   store_object_id=store.id,
                                   facebook_user_id=data.get('facebook_user_id'))
        account = access.accounts.filter(pk=data.get('id'))
        account.delete()

        return JsonResponse({'success': True})

    def post_facebook_remove(self, request, user, data):
        store_type = data.get('store_type')
        store = utils.get_store_from_request(request, store_type)
        store_content_type = ContentType.objects.get_for_model(store)
        access = get_object_or_404(models.FacebookAccess,
                                   user=request.user.models_user,
                                   store_content_type=store_content_type,
                                   store_object_id=store.id,
                                   facebook_user_id=data.get('facebook_user_id'))

        access.access_token = ''
        access.expires_in = None
        access.save()

        return JsonResponse({'success': True})
