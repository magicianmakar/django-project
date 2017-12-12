import json

from math import ceil
from time import sleep
from pytz import utc

import requests

from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import validate_email
from django.utils import timezone

from raven.contrib.django.raven_compat.models import client as raven_client

from .models import LeadDynoAffiliate, LeadDynoVisitor, LeadDynoLead, \
    LeadDynoPurchase, LeadDynoSync


class LeadDynoAffiliations():
    base_url = 'https://api.leaddyno.com/v1'
    max_records_per_page = 100.0
    sync_expiration_time = timezone.timedelta(hours=2)

    def __init__(self):
        self.last_sync = LeadDynoSync.objects.first()

        # Only needed for the first time affiliations is run
        # TODO: Move to migrations scripts
        if self.last_sync is None:
            self.last_sync = LeadDynoSync.objects.create(
                last_synced_visitor=LeadDynoVisitor.objects.first(),
                last_synced_lead=LeadDynoLead.objects.first(),
                last_synced_purchase=LeadDynoPurchase.objects.first(),
                count_visitors=LeadDynoVisitor.objects.count(),
                count_leads=LeadDynoLead.objects.count(),
                count_purchases=LeadDynoPurchase.objects.count()
            )

            now = timezone.now() - self.sync_expiration_time
            self.last_sync.created_at = now
            self.last_sync.save()

        self.current_sync = self.last_sync

    def _get_response_from_url(self, url, params={}):
        request_url = self.base_url + url
        params['key'] = settings.LEAD_DYNO_API_KEY
        return requests.get(request_url, params=params)

    def _post_response_from_url(self, url, data={}):
        request_url = self.base_url + url
        data['key'] = settings.LEAD_DYNO_API_KEY
        return requests.post(request_url, json=data)

    def _put_response_from_url(self, url, data={}):
        request_url = self.base_url + url
        data['key'] = settings.LEAD_DYNO_API_KEY
        return requests.put(request_url, json=data)

    def get_affiliates_count(self):
        url = '/affiliates/count'

        result = self._get_response_from_url(url)
        json_response = result.json()
        print 'COUNT:', result.text
        return json_response['count']

    def get_affiliates(self, page=1):
        url = '/affiliates'
        params = {'page': page}

        result = self._get_response_from_url(url, params)
        affiliates = result.json()

        return affiliates

    def fetch_all_affiliates(self):
        affiliates_count = self.get_affiliates_count()

        affiliates = []
        pages = int(ceil(affiliates_count / self.max_records_per_page))
        for page in range(1, pages + 1):
            affiliates = self.get_affiliates(page)

            # Check if rate limit might have been reached
            if isinstance(affiliates, dict) and \
                    affiliates.get('message').index('limit exceeded') > -1:
                sleep(60)
                affiliates = self.get_affiliates(page)

            for affiliate in affiliates:
                email = affiliate.get('email')
                users = User.objects.filter(email=email)
                user = users.first() if users.exists() else None

                affiliate_obj, created = LeadDynoAffiliate.objects.get_or_create(
                    affiliation_id=affiliate.get('id'),
                    defaults={
                        'user': user,
                        'email': email,
                        'first_name': affiliate.get('first_name') or '',
                        'last_name': affiliate.get('last_name') or '',
                        'affiliate_dashboard_url': affiliate.get('affiliate_dashboard_url'),
                        'affiliate_url': affiliate.get('affiliate_url'),
                    }
                )

                LeadDynoVisitor.objects.filter(affiliate_email=email).update(affiliate=affiliate_obj)
                LeadDynoLead.objects.filter(affiliate_email=email).update(affiliate=affiliate_obj)
                LeadDynoPurchase.objects.filter(affiliate_email=email).update(affiliate=affiliate_obj)

            sleep(2)

    def get_visitors_count(self):
        url = '/visitors/count'
        result = self._get_response_from_url(url)
        print result.text
        return result.json()['count']

    def get_visitors(self, page=1):
        url = '/visitors'
        params = {'page': page}

        result = self._get_response_from_url(url, params)
        status_code = result.status_code

        while status_code != 200:
            sleep(10)
            result = self._get_response_from_url(url, params)
            status_code = result.status_code

        return result.json()

    def count_remaining_visitors(self):
        return self.get_visitors_count() - self.last_sync.count_visitors

    def fetch_remaining_visitors(self, as_generator=False):
        visitors_count = self.count_remaining_visitors()
        last_visitor = self.last_sync.last_synced_visitor

        # Visitors ordered by a descendant created_at field
        pages = int(ceil(visitors_count / self.max_records_per_page))
        for page in range(1, pages + 1)[::-1]:
            new_visitors = []
            fetched_visitors = self.get_visitors(page)

            # Check if rate limit might have been reached
            if isinstance(fetched_visitors, dict) and \
                    fetched_visitors.get('message').index('limit exceeded') > -1:
                sleep(60)
                fetched_visitors = self.get_visitors(page)

            for visitor in fetched_visitors:
                if as_generator:
                    yield visitor.get('id')

                created_at = utc.localize(timezone.datetime.strptime(visitor.get('created_at'),
                                                                     '%Y-%m-%dT%H:%M:%SZ'))

                # Only parses and save visitors that arent added yet
                if last_visitor is not None and last_visitor.created_at >= created_at:
                    continue

                # Look for affiliate if exists
                affiliate = None
                affiliate_email = ''
                if visitor.get('affiliate'):
                    found_affiliates = LeadDynoAffiliate.objects.filter(
                        affiliation_id=visitor['affiliate'].get('id'))

                    affiliate_email = visitor['affiliate'].get('email')
                    if found_affiliates.exists():
                        affiliate = found_affiliates.first()

                url = ''
                if visitor.get('url'):
                    url = visitor.get('url').get('url')

                new_visitors.append(
                    LeadDynoVisitor(affiliate=affiliate,
                                    affiliate_email=affiliate_email,
                                    original_data=json.dumps(visitor),
                                    visitor_id=visitor.get('id'),
                                    created_at=created_at,
                                    tracking_code=visitor.get('tracking_code'),
                                    url=url)
                )

            LeadDynoVisitor.objects.bulk_create(new_visitors)
            sleep(2)

    def get_leads_count(self):
        url = '/leads/count'

        result = self._get_response_from_url(url)
        json_response = result.json()

        return json_response['count']

    def get_leads(self, page=1):
        url = '/leads'
        params = {'page': page}

        result = self._get_response_from_url(url, params)
        status_code = result.status_code

        while status_code != 200:
            sleep(10)
            result = self._get_response_from_url(url, params)
            status_code = result.status_code

        return result.json()

    def count_remaining_leads(self):
        return self.get_leads_count() - self.last_sync.count_leads

    def fetch_remaining_leads(self, as_generator=False):
        leads_count = self.count_remaining_leads()
        last_lead = self.last_sync.last_synced_lead

        # Leads ordered by a descendant created_at field
        pages = int(ceil(leads_count / self.max_records_per_page))
        for page in range(1, pages + 1)[::-1]:
            new_leads = []
            leads = self.get_leads(page)

            # Check if rate limit might have been reached
            if isinstance(leads, dict) and \
                    leads.get('message').index('limit exceeded') > -1:
                sleep(60)
                leads = self.get_leads(page)

            for lead in leads:
                if as_generator:
                    yield lead.get('id')

                created_at = utc.localize(timezone.datetime.strptime(lead.get('created_at'),
                                                                     '%Y-%m-%dT%H:%M:%SZ'))

                # Only parses and save leads that arent added yet
                if last_lead is not None and last_lead.created_at >= created_at:
                    continue

                # Look for affiliate if exists
                affiliate = None
                affiliate_email = ''
                if lead.get('affiliate'):
                    found_affiliates = LeadDynoAffiliate.objects.filter(
                        affiliation_id=lead['affiliate'].get('id'))

                    affiliate_email = lead['affiliate'].get('email')
                    if found_affiliates.exists():
                        affiliate = found_affiliates.first()

                new_leads.append(
                    LeadDynoLead(affiliate=affiliate,
                                 affiliate_email=affiliate_email,
                                 original_data=json.dumps(lead),
                                 lead_id=lead.get('id'),
                                 email=lead.get('email'),
                                 created_at=created_at)
                )

            LeadDynoLead.objects.bulk_create(new_leads)
            sleep(2)

    def get_purchases_count(self):
        url = '/purchases/count'

        result = self._get_response_from_url(url)
        json_response = result.json()

        return json_response['count']

    def get_purchases(self, page=1):
        url = '/purchases'
        params = {'page': page}

        result = self._get_response_from_url(url, params)
        status_code = result.status_code

        while status_code != 200:
            sleep(10)
            result = self._get_response_from_url(url, params)
            status_code = result.status_code

        return result.json()

    def count_remaining_purchases(self):
        return self.get_purchases_count() - self.last_sync.count_purchases

    def fetch_remaining_purchases(self, as_generator=False):
        purchases_count = self.count_remaining_purchases()
        last_purchase = self.last_sync.last_synced_purchase

        # Leads ordered by a descendant created_at field
        pages = int(ceil(purchases_count / self.max_records_per_page))
        for page in range(1, pages + 1)[::-1]:
            new_purchases = []
            purchases = self.get_purchases(page)

            # Check if rate limit might have been reached
            if isinstance(purchases, dict) and \
                    purchases.get('message').index('limit exceeded') > -1:
                sleep(60)
                purchases = self.get_purchases(page)

            for purchase in purchases:
                if as_generator:
                    yield purchase.get('id')

                created_at = utc.localize(timezone.datetime.strptime(purchase.get('created_at'),
                                                                     '%Y-%m-%dT%H:%M:%SZ'))

                # Only parses and save leads that arent added yet
                if last_purchase is not None and last_purchase.created_at >= created_at:
                    continue

                # Look for affiliate if exists
                affiliate = None
                affiliate_email = ''
                if purchase.get('affiliate'):
                    found_affiliates = LeadDynoAffiliate.objects.filter(
                        affiliation_id=purchase['affiliate'].get('id'))

                    affiliate_email = purchase['affiliate'].get('email')
                    if found_affiliates.exists():
                        affiliate = found_affiliates.first()

                new_purchases.append(
                    LeadDynoPurchase(affiliate=affiliate,
                                     affiliate_email=affiliate_email,
                                     original_data=json.dumps(purchase),
                                     purchase_id=purchase.get('id'),
                                     purchase_code=purchase.get('purchase_code'),
                                     created_at=created_at)
                )

            LeadDynoPurchase.objects.bulk_create(new_purchases)
            sleep(2)

    def check_last_update(self):
        from .tasks import sync_lead_dyno_resources

        # Check if the last sync was expired
        sync_lead_dyno_resources.delay()

    def sync(self):
        self.current_sync = LeadDynoSync.objects.create()
        self.fetch_remaining_visitors()
        self.fetch_remaining_leads()
        self.fetch_remaining_purchases()

    def finish_sync(self, resync=False):
        self.current_sync.last_synced_visitor = LeadDynoVisitor.objects.first()
        self.current_sync.last_synced_lead = LeadDynoLead.objects.first()
        self.current_sync.last_synced_purchase = LeadDynoPurchase.objects.first()
        self.current_sync.count_visitors = LeadDynoVisitor.objects.count()
        self.current_sync.count_leads = LeadDynoLead.objects.count()
        self.current_sync.count_purchases = LeadDynoPurchase.objects.count()

        if resync:
            self.current_sync.created_at = timezone.now() - self.sync_expiration_time

        self.current_sync.save()

        self.last_sync = self.current_sync


class LeadDynoAffiliation(LeadDynoAffiliations):

    def __init__(self, user):
        self.user = user

        raven_client.user_context({
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email
        })

        try:
            self.affiliation = self.user.lead_dyno_affiliation
        except User.RelatedObjectDoesNotExist:
            import traceback; traceback.print_exc();
            self.affiliation = None

    def update(self, email=None, first_name=None, last_name=None):
        affiliation_id = self.affiliation.affiliation_id

        # Validate e-mail if changed
        if email is not None and email != self.affiliation.email:
            validate_email(email)

            # If e-mail exists in API, set new id
            api_affiliation_id = self.affiliation_email_exists(email)
            if api_affiliation_id:
                affiliation_id = api_affiliation_id

                # E-mail shouldn't be on database already
                if LeadDynoAffiliate.objects.filter(email=email).exists():
                    raise Exception('This e-mail is already tied to an account, ' +
                                    'contact us if you are the owner.')

        # Update affiliation
        url = '/affiliates/{}'.format(affiliation_id)

        data = {}
        if email is not None:
            data['email'] = email
        if first_name is not None:
            data['first_name'] = first_name
        if last_name is not None:
            data['last_name'] = last_name

        result = self._put_response_from_url(url, data)
        affiliate = result.json()

        email = affiliate.get('email')
        self.affiliation.affiliation_id = affiliate.get('id')
        self.affiliation.email = email
        self.affiliation.first_name = affiliate.get('first_name')
        self.affiliation.last_name = affiliate.get('last_name')
        self.affiliation.affiliate_dashboard_url = affiliate.get('affiliate_dashboard_url')
        self.affiliation.affiliate_url = affiliate.get('affiliate_url')
        self.affiliation.save()

        self.affiliation.visitors.update(affiliate_email=email)
        self.affiliation.leads.update(affiliate_email=email)
        self.affiliation.purchases.update(affiliate_email=email)

        return affiliate

    def check_affiliation(self):
        url = '/affiliates'

        data = {
            "email": self.user.email,
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
        }

        result = self._post_response_from_url(url, data)
        affiliate_user = result.json()

        email = affiliate_user.get('email')
        affiliate, created = LeadDynoAffiliate.objects.get_or_create(
            affiliation_id=affiliate_user.get('id'),
            defaults={
                'user': self.user,
                'email': email,
                'first_name': affiliate_user.get('first_name'),
                'last_name': affiliate_user.get('last_name'),
                'affiliate_dashboard_url': affiliate_user.get('affiliate_dashboard_url'),
                'affiliate_url': affiliate_user.get('affiliate_url'),
            }
        )

        LeadDynoVisitor.objects.filter(affiliate_email=email).update(affiliate=affiliate)
        LeadDynoLead.objects.filter(affiliate_email=email).update(affiliate=affiliate)
        LeadDynoPurchase.objects.filter(affiliate_email=email).update(affiliate=affiliate)

        return affiliate_user

    def affiliate_leads(self):
        if self.affiliation is None:
            return []

        url = '/affiliates/{}/leads'.format(self.affiliation.affiliation_id)

        result = self._get_response_from_url(url)
        affiliate_leads = result.json()

        return affiliate_leads

    def affiliate_commissions(self):
        if self.affiliation is None:
            return []

        url = '/affiliates/{}/commissions'.format(self.affiliation.affiliation_id)

        result = self._get_response_from_url(url)
        affiliate_commissions = result.json()

        return affiliate_commissions

    def get_affiliate(self, email=None, affiliate_id=None):
        params = {}
        if email is not None:
            url = '/affiliates/by_email'
            params['email'] = email
        else:
            url = '/affiliates/{}'.format(affiliate_id)

        result = self._get_response_from_url(url, params=params)

        return result.json()

    def affiliation_email_exists(self, email):
        affiliate = self.get_affiliate(email=email)
        if affiliate is None:
            return False
        else:
            return affiliate['id']
