from datetime import date

from django.utils import timezone
from django.db.models import Q
from tqdm import tqdm
from raven.contrib.django.raven_compat.models import client as raven_client
from facebookads.exceptions import FacebookRequestError

from shopified_core.management import DropifiedBaseCommand
from profit_dashboard.models import FacebookAccess
from profit_dashboard.utils import create_facebook_ads


def attach_account(account, stdout=None):
    try:
        # Return already formatted insights
        for insight in account.get_api_insights():
            create_facebook_ads(account, insight)

        account.last_sync = date.today()
        account.save()

    except FacebookRequestError, e:
        if e.api_error_code() == 17:  # (#17) User request limit reached
            raven_client.captureException(level='warning')
            stdout.write('Facebook API limit')

        elif e.api_error_code() == 190:  # (#190) Error validating access token
            facebook_access = account.access
            facebook_access.access_token = ''
            facebook_access.expires_in = None
            facebook_access.save()

            raven_client.captureException(level='warning')
            stdout.write('Facebook Invalid Token')

        else:
            raven_client.captureException()

        stdout.write(' * API Call error: {}'.format(repr(e)))

    except Exception:
        raven_client.captureException()
        stdout.write(' * Error: {}'.format(repr(e)))


class Command(DropifiedBaseCommand):
    help = 'Sync Aliexpress fulfillment costs from last month'

    def add_arguments(self, parser):
        parser.add_argument('--progress', dest='progress', action='store_true', help='Show Progress')

    def start_command(self, *args, **options):
        progress = options['progress']

        facebook_access_list = FacebookAccess.objects.filter(~Q(access_token=''), expires_in__gt=timezone.now())
        count = len(facebook_access_list)
        self.write('Syncing {} Facebook Accounts'.format(count))

        if progress:
            obar = tqdm(total=count)

        for access in facebook_access_list:
            for account in access.accounts.all():
                attach_account(
                    account=account,
                    stdout=self.stdout
                )

            if progress:
                obar.update(1)

        if progress:
            obar.close()
