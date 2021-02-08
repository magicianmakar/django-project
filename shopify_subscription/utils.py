import requests
from django.conf import settings
from django.urls import reverse
from shopified_core.utils import app_link, safe_float, last_executed, send_email_from_template


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
    if shopify_subscription:
        amount = safe_float(amount)
        if shopify_subscription.balance_remaining < amount:
            # adjusting capped limit by $50 (to not ask to recap very often)
            shopify_subscription.customize(capped_amount=safe_float(shopify_subscription.capped_amount) + 50)

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
