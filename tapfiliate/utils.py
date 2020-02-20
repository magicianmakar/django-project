import arrow
import requests

from django.conf import settings

from stripe_subscription.stripe_api import stripe
from tapfiliate.models import TapfiliateCommissions
from django.contrib.auth.models import User
from analytic_events.models import SuccessfulPaymentEvent
import simplejson as json


def requests_session():
    s = requests.Session()
    s.headers.update({
        'Api-Key': settings.TAPFILIATE_API_KEY
    })

    return s


def find_conversation_from_stripe(customer_id):
    rep = requests_session().get(
        url='https://api.tapfiliate.com/1.6/conversions/',
        params={
            'external_id': customer_id
        }
    )

    rep.raise_for_status()

    if not len(rep.json()):
        return None

    elif len(rep.json()) > 1:
        raise Exception('More Than One Conversion')

    return rep.json()[0]


def add_commission_from_stripe(charge_id):
    charge = stripe.Charge.retrieve(charge_id)

    customer_id = charge.customer
    conversion = find_conversation_from_stripe(customer_id)
    if not conversion:
        return

    customer = stripe.Customer.retrieve(customer_id)

    try:
        affiliate = get_affiliate(conversion['affiliate']['id'])
        lifetime_comissions_flag = affiliate['meta_data'].get('lifetime_comissions_flag')
    except:
        lifetime_comissions_flag = False

    if lifetime_comissions_flag != '1' and arrow.get(customer.created).replace(years=1) < arrow.utcnow():
        # User registered more than 12 months ago, ignore any further commissions
        return

    amount = 0
    invoice = stripe.Invoice.retrieve(charge.invoice)
    for i in invoice.lines:
        if i.plan:
            amount = min(amount, i.plan.amount) if amount else i.plan.amount

    if not amount:
        return

    amount = amount / 100.0

    data = {
        'conversion_sub_amount': amount
    }

    if conversion['affiliate']['id'] in ['cedricdufay']:
        data['commission_type'] = 'preferred'

    rep = requests_session().post(
        url='https://api.tapfiliate.com/1.6/conversions/{}/commissions/'.format(conversion['id']),
        json=data
    )

    rep.raise_for_status()

    commissions = rep.json()
    for commission in commissions:
        TapfiliateCommissions.objects.create(
            commission_id=commission['id'],
            conversion_id=conversion['id'],
            affiliate_id=conversion['affiliate']['id'],
            charge_id=charge.id,
            customer_id=customer_id)


def add_successful_payment(charge_id):
    charge = stripe.Charge.retrieve(charge_id)
    try:
        user = User.objects.get(stripe_customer__customer_id=charge.customer)
    except User.DoesNotExist:
        raise Exception('Stripe customer not found')

    SuccessfulPaymentEvent.objects.create(user=user, charge=json.dumps({
        'charge': charge.to_dict(),
        'count': len(stripe.Charge.list(customer=charge.customer).data)
    }))


def get_affiliate(affiliate_id):
    rep = requests_session().get(
        url='https://api.tapfiliate.com/1.6/affiliates/{}/'.format(affiliate_id)
    )

    rep.raise_for_status()

    if not rep.json():
        return None

    return rep.json()
