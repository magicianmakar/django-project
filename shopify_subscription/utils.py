from datetime import timedelta
from decimal import Decimal

import arrow
import requests

from django.conf import settings
from django.utils.functional import cached_property
from django.urls import reverse
from fulfilment_fee.models import SaleTransactionFee
from shopified_core.utils import app_link, safe_float, last_executed, send_email_from_template
from django.db.models import Sum


def get_application_charge_price(application_charge):
    return Decimal(application_charge.to_dict()['price'])


def get_active_charge(recurring_charges):
    for charge in recurring_charges:
        if charge.status == 'active':
            return charge


def get_charge_name(charge):
    return charge.to_dict().get('name', '')


class YearlySubscription:
    def __init__(self, profile):
        self._profile = profile

    @cached_property
    def is_active(self):
        return self.charge.to_dict().get('status') in ['active', 'accepted']

    @cached_property
    def start_date(self):
        created_at = self.charge.to_dict().get('created_at')

        return arrow.get(created_at) if created_at else None

    @cached_property
    def end_date(self):
        return self.start_date.shift(years=1) if self.start_date else None

    @cached_property
    def next_renewal_date(self):
        return self.end_date

    @cached_property
    def total_contract_amount(self):
        return self._get_total_contract_amount()

    @cached_property
    def charge(self):
        return self._get_charge()

    def _get_total_contract_amount(self):
        total_price = self._profile.application_charge_total
        self_price = get_application_charge_price(self.charge)

        return total_price - self_price

    def _get_charge(self):
        charges = self._profile.application_charges
        for charge in charges:
            if f"Dropified {self._profile.plan.title}" in get_charge_name(charge):
                if charge.status == 'active':
                    return charge


class RecurringSubscription:
    def __init__(self, profile):
        self._profile = profile

    @cached_property
    def is_active(self):
        return self.charge.to_dict().get('status') == 'active'

    @cached_property
    def start_date(self):
        activated_on = self.charge.to_dict().get('activated_on')

        return arrow.get(activated_on) if activated_on else None

    @cached_property
    def end_date(self):
        if self.start_date:
            end_date = self.start_date.datetime + timedelta(days=30)
            return arrow.get(end_date)

    @cached_property
    def next_renewal_date(self):
        billing_on = self.charge.to_dict().get('billing_on')

        return arrow.get(billing_on) if billing_on else None

    @cached_property
    def total_contract_amount(self):
        return self._profile.application_charge_total + self.balanced_used

    @cached_property
    def balanced_used(self):
        try:
            balanced_used = self.charge.to_dict().get('balanced_used', 0)

            return Decimal(balanced_used).quantize(Decimal('1.00'))
        except:
            return 0.0

    @cached_property
    def charge(self):
        return get_active_charge(self._profile.recurring_charges)


class ShopifyProfile:
    def __init__(self, user):
        self._user = user
        self._subscription = self._get_subscription() if self.plan else None

    @cached_property
    def plan(self):
        return getattr(self._user.profile, "plan")

    @cached_property
    def has_free_plan(self):
        return bool(self.plan and self.plan.free_plan)

    @cached_property
    def has_other_free(self):
        return bool(self.plan and (self.plan.is_free or self.plan.is_active_free))

    @cached_property
    def is_valid(self):
        return bool(self.shopify_store)

    @cached_property
    def shopify_store(self):
        return self._user.profile.get_shopify_stores().first()

    @cached_property
    def is_active(self):
        return self._subscription.is_active and not self.has_free_plan and not self.has_other_free

    @cached_property
    def start_date(self):
        return self._subscription.start_date

    @cached_property
    def end_date(self):
        return self._subscription.end_date

    @cached_property
    def next_renewal_date(self):
        return self._subscription.next_renewal_date

    @cached_property
    def total_contract_amount(self):
        return self._subscription.total_contract_amount

    @cached_property
    def application_charges(self):
        try:
            return self._get_application_charges()
        except:
            return []

    @cached_property
    def recurring_charges(self):
        try:
            return self._get_recurring_charges()
        except:
            return []

    @cached_property
    def application_charge_total(self):
        return self._get_application_charge_total()

    def _get_subscription(self):
        yearly = self.plan.payment_interval == 'yearly'

        return YearlySubscription(self) if yearly else RecurringSubscription(self)

    def _get_application_charges(self):
        return self.shopify_store.shopify.ApplicationCharge.find()

    def _get_recurring_charges(self):
        return self.shopify_store.shopify.RecurringApplicationCharge.find()

    def _get_application_charge_total(self):
        total = Decimal('0.00')

        for charge in self.application_charges:
            total += get_application_charge_price(charge)

        return total


class BaremetricsRequest():
    _base_url = 'https://api.baremetrics.com/v1'
    headers = {
        'Authorization': 'Bearer {}'.format(settings.BAREMETRICS_API_KEY),
        'Accept': 'application/json'
    }

    def __init__(self, source_id=None):
        if source_id:
            self._source_id = source_id

    @property
    def source_id(self):
        if not hasattr(self, '_source_id'):
            self.reload_source_id()

        return self._source_id

    def get_endpoint(self, url=''):
        if url and url[0] != '/':
            url = '/{}'.format(url)

        try:
            url = url.format(source_id=self.source_id)
        except:
            pass

        return '{}{}'.format(self._base_url, url)

    def reload_source_id(self, provider='baremetrics'):
        response = requests.get('{}/sources'.format(self._base_url), headers=self.headers)
        response.raise_for_status()
        for source in response.json().get('sources', []):
            if source.get('provider') == provider:
                self._source_id = source.get('id')
                break

    def get(self, url, *args, **kwargs):
        response = requests.get(self.get_endpoint(url), headers=self.headers, *args, **kwargs)
        response.raise_for_status()
        return response

    def post(self, url, *args, **kwargs):
        response = requests.post(self.get_endpoint(url), headers=self.headers, *args, **kwargs)
        response.raise_for_status()
        return response

    def put(self, url, *args, **kwargs):
        response = requests.put(self.get_endpoint(url), headers=self.headers, *args, **kwargs)
        response.raise_for_status()
        return response


def add_shopify_usage_invoice(user, invoice_type, amount, description="Usage for"):
    # getting last created active shopify subscriptioon
    shopify_subscription = get_shopify_recurring(user)
    charge_id = False
    total_unpaid = SaleTransactionFee.objects.filter(processed=False, user_id=user.id).aggregate(Sum('fee_value')).get('fee_value__sum', 0)

    if shopify_subscription:
        amount = safe_float(amount)
        if shopify_subscription.balance_remaining < amount:
            # adjusting capped limit by $50 (to not ask to recap very often)
            shopify_subscription.customize(capped_amount=safe_float(shopify_subscription.capped_amount) + total_unpaid + 1)

            # refresh shopify sub to use capp increase lin in email
            shopify_subscription = get_shopify_recurring(user)
            user.profile.get_current_shopify_subscription().refresh(shopify_subscription)

            profile_link = app_link(reverse('user_profile'))

            if not user.profile.plan.is_free and not last_executed(f'shopify_capped_limit_u_{user.id}', 3600 * 24):
                send_email_from_template(
                    tpl='shopify_capped_limit_warning.html',
                    subject='Shopify Subscription - actions required',
                    recipient=user.email,
                    data={
                        'profile_link': f'{profile_link}#plan',
                        'shopify_subscription': shopify_subscription
                    }
                )

        store = user.profile.get_shopify_stores().first()
        # adding usage charge item
        charge = store.shopify.UsageCharge.create({
            "test": settings.DEBUG,
            "recurring_application_charge_id": shopify_subscription.id,
            "description": f'{description} {invoice_type}'.strip(),
            "price": amount

        })
        charge_id = charge.id

    return charge_id


def get_shopify_recurring(user):
    active_recurring = False
    try:
        store = user.profile.get_shopify_stores().first()
        recurrings = store.shopify.RecurringApplicationCharge.find()

        for recurring in recurrings:
            if recurring.status == 'active':
                active_recurring = recurring
    except:
        active_recurring = False
    return active_recurring
