from time import sleep

from django.utils import timezone
from tqdm import tqdm
from raven.contrib.django.raven_compat.models import client as raven_client
from facebookads.exceptions import FacebookRequestError

from shopified_core.management import DropifiedBaseCommand
from profit_dashboard.models import FacebookAccount
from profit_dashboard.utils import get_facebook_ads


class Command(DropifiedBaseCommand):
    help = 'Sync Aliexpress fulfillment costs from last month'

    def add_arguments(self, parser):
        parser.add_argument('--noprogress', dest='progress', action='store_false',
                            help='Hide Progress')

    def start_command(self, *args, **options):
        progress = options['progress']

        facebook_accounts_list = FacebookAccount.objects.filter(access__expires_in__gt=timezone.now())
        count = facebook_accounts_list.count()
        if progress:
            obar = tqdm(total=count)

        start = 0

        for account in facebook_accounts_list:
            kwargs = {
                'user': account.access.user,
                'store': account.store,
                'access_token': account.access.access_token,
                'account_ids': account.access.account_ids.split(','),
                'campaigns': account.access.campaigns.split(','),
                'config': account.config,
            }

            try:
                get_facebook_ads(**kwargs)

                start += 1
                if progress:
                    obar.update(1)

            except FacebookRequestError, e:
                if e.api_error_code() == 17:  # (#17) User request limit reached
                    sleep(30)
                    # Another API error at this point means sleep should be increased
                    get_facebook_ads(**kwargs)  # Retry last one

            except Exception, e:
                raven_client.captureException()
                break

        if progress:
            obar.close()
