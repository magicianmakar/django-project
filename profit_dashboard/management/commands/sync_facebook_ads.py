from datetime import date

from django.utils import timezone
from django.db.models import Q
from lib.exceptions import capture_exception
from facebook_business.exceptions import FacebookRequestError

from shopified_core.commands import DropifiedBaseCommand
from profit_dashboard.models import FacebookAccess
from profit_dashboard.utils import create_facebook_ads


def attach_account(account, stdout=None):
    try:
        # Return already formatted insights
        for insight in account.get_api_insights():
            create_facebook_ads(account, insight)

        account.last_sync = date.today()
        account.save()

    except FacebookRequestError as e:
        if e.api_error_code() == 17:  # (#17) User request limit reached
            capture_exception(level='warning')
            stdout.write('Facebook API limit')

        elif e.api_error_code() == 190:  # (#190) Error validating access token
            facebook_access = account.access
            facebook_access.expires_in = None
            facebook_access.save()

            capture_exception(level='warning')
            stdout.write('Facebook Invalid Token')

        else:
            capture_exception()

        stdout.write(' * API Call error: {}'.format(repr(e)))

    except Exception as e:
        capture_exception()
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
            self.progress_total(count)

        for access in facebook_access_list:
            # Update token if its about to expire
            try:
                access.get_or_update_token()
            except:
                pass

            for account in access.accounts.all():
                attach_account(
                    account=account,
                    stdout=self.stdout
                )

            self.progress_update()

        self.progress_close()
