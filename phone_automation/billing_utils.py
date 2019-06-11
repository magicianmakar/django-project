from shopified_core.utils import safe_int, safe_float

from typing import Dict
from django.contrib.auth.models import User
from stripe_subscription.stripe_api import stripe
from . import utils as utils
from django.conf import settings


class CallflexOveragesBilling:

    def __init__(self, user):
        # type: (User) -> ...
        self.user = user

    def add_invoice(self, invoice_type, amount, replace_flag=False, description="CallFlex Overages for"):
        # type: (Dict, float) -> ...
        # adding stripe invoice item
        upcoming_invoice = stripe.Invoice.upcoming(customer=self.user.stripe_customer.customer_id)
        upcoming_invoice_item = False

        for item in upcoming_invoice['lines']['data']:
            try:
                if item['metadata']['type'] == invoice_type:
                    upcoming_invoice_item = item
            except:
                pass

        if upcoming_invoice_item:
            if replace_flag:
                new_amount = amount * 100
            else:
                new_amount = safe_float(upcoming_invoice_item['metadata']['exact_amount']) + (amount * 100)

            stripe.InvoiceItem.modify(
                upcoming_invoice_item['id'],
                amount=safe_int(new_amount),
                metadata={"type": invoice_type, "exact_amount": new_amount}
            )
        else:
            upcoming_invoice_item = stripe.InvoiceItem.create(
                customer=self.user.stripe_customer.customer_id,
                amount=safe_int(amount * 100),
                currency='usd',
                description=description + ' ' + invoice_type,
                metadata={"type": invoice_type, "exact_amount": (amount * 100)}
            )

        return upcoming_invoice_item

    def update_overages(self):
        # update phone number overages

        # getting number of 'monthes' passed after last invoice date (to process yearly subs)
        subscription_period_start = utils.get_callflex_subscription_start(self.user)
        month_passed = utils.get_monthes_passed(subscription_period_start)

        overages_phone_number = 0

        phonenumber_usage_tollfree = utils.get_phonenumber_usage(self.user, "tollfree")
        phonenumber_usage_local = utils.get_phonenumber_usage(self.user, "local")

        if phonenumber_usage_tollfree['total'] is not False and phonenumber_usage_tollfree['used'] >= phonenumber_usage_tollfree['total']:
            overages_phone_number += (phonenumber_usage_tollfree['used'] - phonenumber_usage_tollfree['total']) * \
                settings.EXTRA_TOLLFREE_NUMBER_PRICE * (month_passed + 1)

        if phonenumber_usage_local['total'] is not False and phonenumber_usage_local['used'] >= phonenumber_usage_local['total']:
            overages_phone_number += (phonenumber_usage_local['used'] - phonenumber_usage_local['total']) * \
                settings.EXTRA_LOCAL_NUMBER_PRICE * (month_passed + 1)

        self.add_invoice('extra_number', overages_phone_number, True)

        # update minutes overages
        overages_minutes = 0
        total_duration_tollfree = utils.get_month_totals(self.user, "tollfree")
        total_duration_local = utils.get_month_totals(self.user, "local")

        total_duration_month_limit_tollfree = utils.get_month_limit(self.user, "tollfree")
        total_duration_month_limit_local = utils.get_month_limit(self.user, "local")

        if total_duration_month_limit_tollfree is not False and total_duration_tollfree and \
                total_duration_tollfree > total_duration_month_limit_tollfree:
            overages_minutes += (total_duration_tollfree - total_duration_month_limit_tollfree) \
                * settings.EXTRA_TOLLFREE_MINUTE_PRICE / 60

        if total_duration_month_limit_local is not False and total_duration_local and \
                total_duration_local > total_duration_month_limit_local:
            overages_minutes += (total_duration_local - total_duration_month_limit_local) \
                * settings.EXTRA_LOCAL_MINUTE_PRICE / 60

        self.add_invoice('extra_minutes', overages_minutes, True)
