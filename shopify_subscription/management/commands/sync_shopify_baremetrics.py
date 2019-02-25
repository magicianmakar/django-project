import arrow
from django.core.cache import cache
from requests.exceptions import HTTPError
from tqdm import tqdm

from shopified_core.management import DropifiedBaseCommand
from leadgalaxy.models import ShopifyStore
from shopify_subscription.models import (
    ShopifySubscription,
    BaremetricsCustomer,
    BaremetricsSubscription,
)
from shopify_subscription.utils import BaremetricsRequest


class Command(DropifiedBaseCommand):
    help = 'Sync shopify store owners and subscriptions with baremetrics'

    def add_arguments(self, parser):
        parser.add_argument(
            '--store', dest='store_id', action='store', type=int,
            help='Sync single store with baremetrics')

        parser.add_argument('--progress', dest='progress', action='store_true', help='Show sync progress')

    def start_command(self, *args, **options):
        store_id = options.get('store_id')
        progress = options.get('progress')

        stores = ShopifyStore.objects.filter(is_active=True)
        if store_id:
            stores = stores.filter(id=store_id)

        if progress:
            progress_bar = tqdm(total=stores.count())

        self.requests = BaremetricsRequest()

        for store in stores:
            if not store.user.profile.from_shopify_app_store():
                continue

            try:
                baremetrics_customer = store.baremetrics_customer
            except BaremetricsCustomer.DoesNotExist:
                baremetrics_customer = self.create_baremetrics_user(store)

            if store.shopifysubscription_set.count() == 0:
                continue

            reccuring_charges = store.shopify.RecurringApplicationCharge.find()
            single_charges = store.shopify.ApplicationCharge.find()
            for charge in reccuring_charges + single_charges:
                # Shopify single charges can be yearly plan subscription or extra credits
                try:
                    shopify_subscription = store.shopifysubscription_set.get(subscription_id=charge.id)
                except ShopifySubscription.DoesNotExist:
                    shopify_subscription = None

                try:
                    baremetrics_subscription = shopify_subscription.baremetrics_subscription
                except BaremetricsSubscription.DoesNotExist:
                    baremetrics_subscription = None

                # ShopifySubscription are created when customer selectes a plan
                if shopify_subscription:
                    if baremetrics_subscription is None:
                        shopify_subscription.refresh(charge)
                        self.send_subscription_to_baremetrics(shopify_subscription, baremetrics_customer)
                    elif baremetrics_subscription.status != charge.status:
                        self.sync_with_baremetrics(charge, baremetrics_subscription)
                else:
                    if charge.status == 'active':
                        self.send_charge_to_baremetrics(shopify_subscription, charge, baremetrics_customer)

            if progress:
                progress_bar.update(1)

        if progress:
            progress_bar.close()

    def create_baremetrics_user(self, store):
        plan = store.user.profile.plan
        data = {
            'name': store.user.get_full_name(),
            'email': store.user.email,
            'notes': 'Plan: {}\nStore: {}'.format(plan.title if plan else 'None', store.shop),
            'oid': 'shopify_{}'.format(store.id)
        }
        r = self.requests.post('/{source_id}/customers', json=data)
        customer = r.json().get('customer')

        baremetrics_customer = BaremetricsCustomer.objects.create(store=store, customer_oid=customer['oid'])
        return baremetrics_customer

    def send_charge_to_baremetrics(self, subscription, charge, customer):
        data = {
            'oid': subscription.id,
            'amount': int(float(charge.price) * 100),  # In cents
            'currency': 'USD',
            'customer_oid': customer.customer_oid,
            'created': arrow.get(charge.created_at).timestamp,
            'status': 'paid' if charge.status == 'active' else 'failed'
        }
        self.requests.post('/{source_id}/charges', json=data)

    def send_subscription_to_baremetrics(self, shopify_subscription, customer):
        # Only activated plans generate MRR
        if shopify_subscription.status != 'active':
            return

        plan = self.get_baremetrics_plan(shopify_subscription)

        canceled_at = None
        if shopify_subscription.subscription.get('cancelled_on'):
            canceled_at = arrow.get(shopify_subscription.subscription.get('cancelled_on')).timestamp

        # Shopify yearly plans are single charges and dont reoccur
        if plan['interval'] == 'year' and canceled_at:
            canceled_at = arrow.get(shopify_subscription.activated_on).replace(days=364)

        data = {
            'oid': 'shopify_{}'.format(shopify_subscription.id),
            'started_at': arrow.get(shopify_subscription.activated_on).timestamp,
            'canceled_at': canceled_at,
            'plan_oid': shopify_subscription.plan.id,
            'customer_oid': customer.customer_oid,
        }
        self.requests.post('/{source_id}/subscriptions', json=data)
        BaremetricsSubscription.objects.create(
            customer=customer,
            shopify=shopify_subscription,
            subscription_oid=data['oid'],
            canceled_at=canceled_at
        )

    def sync_with_baremetrics(self, charge, baremetrics_subscription):
        # Only activated plans generate MRR
        if not charge.activated_on:
            return

        # Only plan subscriptions can change status
        if not baremetrics_subscription.shopify_subscription.plan:
            return

        baremetrics_subscription.shopify_subscription.refresh(charge)

        canceled_at = None
        if charge.cancelled_on:
            canceled_at = arrow.get(charge.cancelled_on)
            baremetrics_subscription.canceled_at = canceled_at.datetime

        baremetrics_subscription.status = charge.status
        baremetrics_subscription.save()

        # Handle baremetrics subscription cancelation only if needed
        if charge.status in ['frozen', 'cancelled', 'declined'] and canceled_at:
            data = {
                'canceled_at': canceled_at.timestamp
            }
            try:
                self.requests.put('/{}/subscriptions/{}/cancel'.format('{source_id}', baremetrics_subscription.subscription_oid), data=data)
            except HTTPError as e:
                if e.response.status_code != 404:
                    raise

    def get_baremetrics_plan(self, subscription):
        plan = subscription.plan

        # Prevent calling baremetrics API too many times
        baremetrics_plan = cache.get('baremetrics_plan_{}'.format(plan.id), None)
        if baremetrics_plan:
            return baremetrics_plan

        # Check plan exists in baremetrics before creating
        try:
            r = self.requests.get('/{}/plans/{}'.format('{source_id}', plan.id))
            baremetrics_plan = r.json().get('plan')
            if baremetrics_plan:
                cache.set('baremetrics_plan_{}'.format(plan.id), baremetrics_plan, timeout=1800)
                return baremetrics_plan
        except HTTPError as e:
            if e.response.status_code != 404:
                raise

        # Plan must exist in baremetrics
        interval = 'month'
        amount = plan.monthly_price
        if plan.payment_interval == 'yearly':
            interval = 'year'
            amount *= 12

        data = {
            'oid': plan.id,
            'name': plan.get_description(),
            'currency': 'USD',
            'amount': int(amount * 100),  # In cents
            'interval': interval,
            'interval_count': 1,
            'trial_duration': plan.trial_days,
            'trial_duration_unit': 'day',
        }
        r = self.requests.post('/{source_id}/plans', json=data)
        baremetrics_plan = r.json().get('plan')

        cache.set('baremetrics_plan_{}'.format(plan.id), baremetrics_plan, timeout=1800)

        return baremetrics_plan
