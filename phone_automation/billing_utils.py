from shopified_core.utils import safe_int, safe_float

from django.contrib.auth.models import User
from stripe_subscription.stripe_api import stripe
from . import utils as utils
from django.conf import settings
from shopified_core.utils import app_link
from shopified_core.utils import send_email_from_template
from django.urls import reverse
from .models import CallflexShopifyUsageCharge
from raven.contrib.django.raven_compat.models import client as raven_client
from shopified_core.utils import last_executed


class CallflexOveragesBilling:

    def __init__(self, user):
        # type: (User) -> ...
        self.user = user

    def add_invoice(self, invoice_type, amount, replace_flag=False, description="CallFlex Overages for"):

        try:
            upcoming_invoice = stripe.Invoice.upcoming(customer=self.user.stripe_customer.customer_id)
        except:
            raven_client.captureMessage("No Upcoming Invoice. Skipping this user.")
            return False

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
        if not subscription_period_start:
            return False
        else:
            invoices = []

        subscription_interval = utils.get_callflex_subscription_period(self.user)
        if subscription_interval == 'year':
            month_passed = utils.get_monthes_passed(subscription_period_start)
        else:
            month_passed = 0

        overages_phone_number = 0

        phonenumber_usage_tollfree = utils.get_phonenumber_usage(self.user, "tollfree")
        phonenumber_usage_local = utils.get_phonenumber_usage(self.user, "local")

        if phonenumber_usage_tollfree['total'] is not False and phonenumber_usage_tollfree['used'] >= phonenumber_usage_tollfree['total']:
            overage_phones = self.user.twilio_phone_numbers.filter(type="tollfree").all()[safe_int(phonenumber_usage_tollfree['total']):]
            # going thru each "overage" number and calculating monther passed (after provisioining or subscription start, which was first
            for overage_phone in overage_phones:
                if overage_phone.created_at > subscription_period_start:
                    month_passed_phone = utils.get_monthes_passed(overage_phone.created_at)
                else:
                    month_passed_phone = month_passed
                overages_phone_number += (phonenumber_usage_tollfree['used'] - phonenumber_usage_tollfree['total']) * \
                    settings.EXTRA_TOLLFREE_NUMBER_PRICE * (month_passed_phone + 1)

        if phonenumber_usage_local['total'] is not False and phonenumber_usage_local['used'] >= phonenumber_usage_local['total']:
            overage_phones = self.user.twilio_phone_numbers.filter(type="local").all()[safe_int(phonenumber_usage_tollfree['total']):]
            # now the same for local numbers
            for overage_phone in overage_phones:
                if overage_phone.created_at > subscription_period_start:
                    month_passed_phone = utils.get_monthes_passed(overage_phone.created_at)
                else:
                    month_passed_phone = month_passed
                overages_phone_number += (phonenumber_usage_local['used'] - phonenumber_usage_local['total']) * \
                    settings.EXTRA_LOCAL_NUMBER_PRICE * (month_passed_phone + 1)

        invoice_numbers = self.add_invoice('extra_number', overages_phone_number, True)
        invoices.append(invoice_numbers)

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

        invoice_minutes = self.add_invoice('extra_minutes', overages_minutes, True)
        invoices.append(invoice_minutes)
        return invoices

    def add_shopify_overages(self):
        overages_phone_number = 0
        phonenumber_usage_tollfree = utils.get_phonenumber_usage(self.user, "tollfree")
        phonenumber_usage_local = utils.get_phonenumber_usage(self.user, "local")
        if phonenumber_usage_tollfree['total'] is not False and phonenumber_usage_tollfree['used'] >= phonenumber_usage_tollfree['total']:
            overages_phone_number += (phonenumber_usage_tollfree['used'] - phonenumber_usage_tollfree['total']) * \
                settings.EXTRA_TOLLFREE_NUMBER_PRICE / 30

        if phonenumber_usage_local['total'] is not False and phonenumber_usage_local['used'] >= phonenumber_usage_local['total']:
            overages_phone_number += (phonenumber_usage_local['used'] - phonenumber_usage_local['total']) * \
                settings.EXTRA_LOCAL_NUMBER_PRICE / 30
        if overages_phone_number > 0:
            self.add_shopify_usage_invoice('extra_number', overages_phone_number, False)

    def add_shopify_usage_invoice(self, invoice_type, amount, charge_only_flag=False, description="CallFlex Overages for"):
        # getting last created active shopify subscriptioon
        shopify_subscription = get_shopify_recurring(self.user)
        charge_id = False
        if shopify_subscription:
            amount = amount
            if shopify_subscription.balance_remaining < amount:
                # adjusting capped limit by $50 (to not ask to recap very often)
                shopify_subscription.customize(capped_amount=safe_float(shopify_subscription.capped_amount) + 50)
                profile_link = app_link(reverse('user_profile'))

                if not self.user.profile.plan.is_free and not last_executed(f'callflex_capped_limit_u_{self.user.id}', 3600 * 24):
                    send_email_from_template(
                        tpl='callflex_shopify_capped_limit_warning.html',
                        subject='CallFlex Subscription - actions required',
                        recipient=self.user.email,
                        data={
                            'profile_link': f'{profile_link}?callflex_anchor#plan'
                        }
                    )

            store = self.user.profile.get_shopify_stores().first()
            # adding usage charge item
            charge = store.shopify.UsageCharge.create({
                "test": settings.DEBUG,
                "recurring_application_charge_id": shopify_subscription.id,
                "description": f'{description} {invoice_type}'.strip(),
                "price": amount

            })
            charge_id = charge.id
        else:
            # no recurring subscription need to delete user's phones
            if not self.user.profile.plan.is_free and not last_executed(f'callflex_shopify_no_subscription_u_{self.user.id}', 3600 * 24):
                profile_link = app_link(reverse('user_profile'))
                send_email_from_template(
                    tpl='callflex_shopify_no_subscription_warning.html',
                    subject='CallFlex Subscription - actions required',
                    recipient=self.user.email,
                    data={
                        'profile_link': f'{profile_link}?callflex_anchor#plan'
                    }
                )
            charge_id = False

        if not charge_id and not charge_only_flag:
            usage_charge = CallflexShopifyUsageCharge()
            usage_charge.user = self.user
            usage_charge.amount = amount
            usage_charge.type = invoice_type
            usage_charge.status = "not_paid"
            usage_charge.save()

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
