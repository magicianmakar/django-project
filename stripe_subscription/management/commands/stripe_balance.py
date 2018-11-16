from tqdm import tqdm

from shopified_core.management import DropifiedBaseCommand
from stripe_subscription.stripe_api import stripe


class EmptyProgress:
    def update(self, n):
        pass

    def close(self):
        pass

    def write(self, s):
        print s


class Command(DropifiedBaseCommand):
    help = 'Find Stripe Customers'

    def add_arguments(self, parser):
        parser.add_argument('--progress', dest='progress', action='store_true', help='Show Check Progress')

    def start_command(self, *args, **options):
        total_count = stripe.Customer.all(limit=1, include=['total_count']).total_count

        self.write_success('Checking {} Customers'.format(total_count))

        if options['progress']:
            obar = tqdm(total=total_count)
        else:
            obar = EmptyProgress()

        customers = stripe.Customer.list(limit=50)
        for customer in customers.auto_paging_iter():
            if customer.account_balance:
                obar.write('{} | {} | {:.02f}$'.format(customer.email, customer.id, customer.account_balance / 100.0))

            obar.update(1)

        obar.close()
