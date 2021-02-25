import re
import arrow
import traceback

from django.contrib.auth.models import User

from last_seen.models import LastSeen
from shopified_core.management import DropifiedBaseCommand
from stripe_subscription.models import StripeCustomer
from stripe_subscription.stripe_api import stripe


class Command(DropifiedBaseCommand):
    help = 'Find Stripe Customers'

    def add_arguments(self, parser):
        parser.add_argument('user_list', type=open, help='Users list filename')

    def start_command(self, *args, **options):
        emails = []
        for line in options['user_list'].readlines():
            tt = re.findall(r'[a-z]*[0-9]{3,}@gmail\.com', line)
            if tt:
                emails.append(line.split(',')[-2])

        self.progress_total(len(emails))
        for email in emails:
            try:
                self.progress_update()
                self.process_email(email)
            except User.DoesNotExist:
                pass
            except KeyboardInterrupt:
                raise
            except:
                traceback.print_exc()

    def process_email(self, email):
        user = User.objects.get(email__iexact=email)
        cus = StripeCustomer.objects.get(user=user)

        try:
            seen = arrow.get(LastSeen.objects.when(user, 'website'))
        except:
            seen = None

        if not seen:
            self.delete_user(user, cus)
        else:
            self.write('>>>>>> Ignore', email, cus.customer_id)

    def delete_user(self, user, cus):
        self.write(f'Delete {user.email} => {cus.customer_id}')
        stripe.Customer.delete(cus.customer_id)
        user.delete()
