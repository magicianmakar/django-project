import json

import arrow
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from addons_core.models import AddonUsage
from last_seen.models import LastSeen
from leadgalaxy.models import UserProfile, AdminEvent, AccountRegistration, PlanRegistration, GroupPlan, FeatureBundle
from leadgalaxy.shopify import ShopifyAPI
from shopified_core.utils import safe_int, url_join, hash_list
from stripe_subscription.stripe_api import stripe
from lib.exceptions import capture_exception


class BaseTemplateView(TemplateView):

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser and not request.user.is_staff:
            raise PermissionDenied()

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['breadcrumbs'] = [{'title': 'ACP', 'url': reverse('acp_index_view')}]

        return ctx


class ACPIndexView(BaseTemplateView):
    template_name = 'acp/index.html'

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['breadcrumbs'].extend(["Index"])

        return ctx


class ACPUserSearchView(BaseTemplateView):
    template_name = 'acp/search.html'

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['breadcrumbs'].extend(["Search"])

        request = self.request
        random_cache = 0
        q = request.GET.get('q') or request.GET.get('user') or request.GET.get('store')

        if q or cache.get('template.cache.acp_users.invalidate'):
            random_cache = arrow.now().timestamp

        users = User.objects.select_related('profile').defer('profile__config').order_by('-date_joined')

        if request.GET.get('plan', None):
            users = users.filter(profile__plan_id=request.GET.get('plan'))

        registrations_email = None

        if q:
            if request.GET.get('store'):
                users = users.filter(
                    Q(shopifystore__id=safe_int(request.GET.get('store')))
                    | Q(shopifystore__shop__iexact=q)
                    | Q(commercehqstore__api_url__icontains=q)
                    | Q(woostore__api_url__icontains=q)
                    | Q(bigcommercestore__api_url__icontains=q)
                    | Q(shopifystore__title__icontains=q)
                )
            elif request.GET.get('user') and safe_int(request.GET.get('user')):
                users = users.filter(id=request.GET['user'])
            else:
                if '@' in q:
                    users = users.filter(Q(email__icontains=q) | Q(profile__emails__icontains=q))
                elif '.myshopify.com' in q:
                    users = users.filter(Q(username__icontains=q) | Q(shopifystore__shop__iexact=q))
                else:
                    users = users.filter(
                        Q(username__icontains=q)
                        | Q(email__icontains=q)
                        | Q(profile__emails__icontains=q)
                        | Q(profile__ips__icontains=q)
                        | Q(shopifystore__shop__iexact=q)
                        | Q(commercehqstore__api_url__icontains=q)
                        | Q(woostore__api_url__icontains=q)
                        | Q(bigcommercestore__api_url__icontains=q)
                        | Q(shopifystore__title__icontains=q)
                    )

            users = users.distinct()

            if not request.user.is_superuser:
                if len(users) > 100:
                    limited_users = []

                    for i in users:
                        limited_users.append(i)

                        if len(limited_users) > 100:
                            break

                    users = limited_users

            profiles = UserProfile.objects.filter(user__in=users)

            if '@' in q:
                registrations_email = q

            AdminEvent.objects.create(
                user=request.user,
                event_type='user_search',
                target_user=users[0] if len(users) == 1 else None,
                data=json.dumps({'query': q}))

        else:
            profiles = UserProfile.objects.filter(user__in=users)

        charges = []
        subscriptions = []
        registrations = []
        user_last_seen = None
        customer_ids = []
        customer_id = request.GET.get('customer_id')
        stripe_customer = None
        shopify_charges = []
        shopify_application_charges = []
        account_registration = None
        logs = []

        if len(users) == 1:
            target_user = users[0]
            target_user.profile.ensure_has_plan()

            for addon_usage in AddonUsage.objects.select_related('billing__addon').filter(user=target_user.id):
                if addon_usage.created_at:
                    logs.append({
                        'key': arrow.get(addon_usage.created_at),
                        'text': '{} addon is installed at {}'
                        .format(addon_usage.billing.addon.title, arrow.get(addon_usage.created_at).format('MM/DD/YYYY HH:mm'))
                    })

                if addon_usage.cancelled_at:
                    logs.append({
                        'key': arrow.get(addon_usage.cancelled_at),
                        'text': '{} addon is uninstalled at {}'
                        .format(addon_usage.billing.addon.title, arrow.get(addon_usage.cancelled_at).format('MM/DD/YYYY HH:mm'))
                    })

            def extract_time(json_obj):
                try:
                    return json_obj['key']
                except KeyError:
                    return 0

            logs.sort(key=extract_time, reverse=True)

            account_registration = AccountRegistration.objects.filter(user=target_user).first()

            rep = requests.get('https://dashboard.stripe.com/v1/search', params={
                'count': 20,
                'include[]': 'total_count',
                'query': 'is:customer {}'.format(target_user.email),
                'facets': 'true'
            }, headers={
                'authorization': 'Bearer {}'.format(settings.STRIPE_SECRET_KEY),
                'content-type': 'application/x-www-form-urlencoded',
            })

            try:
                rep.raise_for_status()

                if rep.json()['count'] > 0:
                    for c in rep.json()['data']:
                        customer_ids.append({'id': c['id'], 'email': c['email']})
            except:
                capture_exception(level='warning')

            if customer_id:
                found = False
                for i in customer_ids:
                    if customer_id == i['id']:
                        found = True
                        break

                assert found

            if not customer_id:
                if target_user.have_stripe_billing():
                    customer_id = target_user.stripe_customer.customer_id
                elif len(customer_ids):
                    customer_id = customer_ids[0]['id']

            invoices = {}
            if customer_id:
                for i in stripe.Charge.list(limit=10, customer=customer_id, expand=['data.dispute']).data:
                    charge = {
                        'id': i.id,
                        'date': arrow.get(i.created).format('MM/DD/YYYY HH:mm'),
                        'date_str': arrow.get(i.created).humanize(),
                        'status': i.status,
                        'dispute': i.dispute,
                        'failure_message': i.failure_message,
                        'amount': '${:0.2f}'.format(i.amount / 100.0),
                        'amount_refunded': '${:0.2f}'.format(i.amount_refunded / 100.0) if i.amount_refunded else None,
                        'receipt_number': i.receipt_number,
                        'receipt_url': i.receipt_url,
                    }

                    if i.invoice:
                        if i.invoice in invoices:
                            inv = invoices[i.invoice]
                        else:
                            inv = stripe.Invoice.retrieve(i.invoice)
                            invoices[i.invoice] = inv

                        charge['invoice'] = {
                            'id': inv.id,
                            'url': inv.hosted_invoice_url,
                        }

                    charges.append(charge)

                for i in stripe.Subscription.list(customer=customer_id).data:
                    subscriptions.append(i)

                stripe_customer = stripe.Customer.retrieve(customer_id)
                stripe_customer.account_balance = stripe_customer.account_balance / 100.0

            registrations_email = target_user.email

            try:
                user_last_seen = arrow.get(LastSeen.objects.when(target_user, 'website')).humanize()
            except:
                user_last_seen = ''

            if target_user.profile.plan.is_shopify:
                for store in target_user.profile.get_shopify_stores():
                    try:
                        for charge in ShopifyAPI(store).recurring_charges():
                            shopify_charges.append(charge)

                        for charge in ShopifyAPI(store).application_charges():
                            shopify_application_charges.append(charge)
                    except:
                        pass

        if registrations_email:
            for i in PlanRegistration.objects.filter(email__iexact=registrations_email):
                i.date = arrow.get(i.created_at).format('MM/DD/YYYY HH:mm')
                i.date_str = arrow.get(i.created_at).humanize()

                registrations.append(i)

            if subscriptions and registrations:
                messages.warning(request, 'You have to cancel monthly subscription if the user is on Lifetime plan')

        plans = GroupPlan.objects.all().order_by('-id')
        bundles = FeatureBundle.objects.all().order_by('-id')

        ctx.update({
            'q': q,
            'users': users,
            'logs': logs,
            'plans': plans,
            'bundles': bundles,
            'profiles': profiles,
            'users_count': len(users),
            'customer_id': customer_id,
            'customer_ids': customer_ids,
            'stripe_customer': stripe_customer,
            'last_charges': charges,
            'subscriptions': subscriptions,
            'registrations': registrations,
            'shopify_charges': shopify_charges,
            'account_registration': account_registration,
            'shopify_application_charges': shopify_application_charges,
            'random_cache': random_cache,
            'user_last_seen': user_last_seen,
            'show_products': request.GET.get('products'),
        })

        return ctx


class ACPPlansView(BaseTemplateView):
    template_name = 'acp/plans.html'

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['breadcrumbs'].extend(["Plans"])

        plans = GroupPlan.objects.all().order_by('-id')

        ctx['plans'] = plans

        return ctx


class ACPCardsView(BaseTemplateView):
    template_name = 'acp/cards.html'

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['breadcrumbs'].extend(["Cards"])
        ctx['cards'] = self.get_all_cards()

        return ctx

    def params(self):
        return {
            'key': 'a83a65bf491b17abe78590ea4d61c225',
            'token': settings.TRELLO_TOKEN
        }

    def get_boards(self, ids=False):
        all_boards = cache.get('boards_lists')
        if not all_boards:
            all_boards = requests.get(
                url=url_join('https://api.trello.com/1/', 'organizations/cs_tdm/boards'),
                params=self.params()
            ).json()

            cache.set('boards_lists', all_boards, timeout=500)

        if ids:
            all_boards = [i['shortLink'] for i in all_boards]

        return all_boards

    def get_boards_lists(self, board, title=None):
        cach_key = f"boards_lists2_{hash_list([board['shortLink'], board['dateLastActivity']])}"
        lists = cache.get(cach_key)
        if not lists:
            lists = requests.get(
                url=url_join('https://api.trello.com/1/', 'boards', board['shortLink'], 'lists'),
                params=self.params()
            ).json()

            cache.set(cach_key, lists, timeout=3600)

        if title:
            lists = [i for i in lists if i['name'].lower() == title.lower()]  # .pop()

        return lists

    def get_list_cards(self, card_id):
        return requests.get(
            url=url_join('https://api.trello.com/1/', 'lists', card_id, 'cards'),
            params=self.params()
        ).json()

    def get_all_cards(self):
        all_cards = []
        for board in self.get_boards():
            for blist in self.get_boards_lists(board, self.request.GET.get('list', 'to do')):
                for card in self.get_list_cards(blist['id']):
                    card['board'] = board
                    card['list'] = blist
                    all_cards.append(card)

        return sorted(all_cards, key=lambda k: k['dateLastActivity'], reverse=True)
