import arrow
from django.core.cache import cache

from shopified_core.commands import DropifiedBaseCommand
from stripe_subscription.stripe_api import stripe


class Command(DropifiedBaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--dry-run', dest='dry_run', action='store_true', help='Show what will be done without actually doing it')

    def start_command(self, *args, **options):
        start_date = cache.get('_stripe_mover_created', 1610563849)
        self.write(f"Find charges from {start_date}")

        charges = stripe.Charge.list(amount=100, created={'gt': start_date})

        counter = 0
        for charge in charges.auto_paging_iter():
            counter += 1
            print(counter, charge.created, charge.id, arrow.get(charge.created).humanize())

            start_date = max(start_date, charge.created)

            if not options['dry_run']:
                stripe.Subscription.create(
                    customer=charge.customer,
                    items=[{
                        'plan': 'SA_6516b30b',
                        'metadata': {
                            'click_funnels': '1',
                            'plod_charge_trial': '1'}
                    }],
                    trial_period_days=14)

        if not options['dry_run']:
            cache.set('_stripe_mover_created', start_date, timeout=3600 * 24)
        else:
            self.write(f'New start date: {start_date}')

        self.write(f'Total users: {counter}')
