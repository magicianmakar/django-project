from Queue import Queue
from threading import Thread
from time import sleep
from datetime import date

from django.utils import timezone
from tqdm import tqdm
from raven.contrib.django.raven_compat.models import client as raven_client
from facebookads.exceptions import FacebookRequestError

from shopified_core.management import DropifiedBaseCommand
from profit_dashboard.models import FacebookAccess
from profit_dashboard.utils import create_facebook_ads


def worker(q):
    while True:
        item = q.get()
        attach_account(**item)
        q.task_done()


def attach_account(account, stdout=None):
    try:
        # Return already formatted insights
        for insight in account.get_api_insights():
            create_facebook_ads(account, insight)

        account.last_sync = date.today()
        account.save()

    except FacebookRequestError, e:
        if e.api_error_code() == 17:  # (#17) User request limit reached
            sleep(30)
            # Another API error at this point means sleep should be increased

            # Retry last one
            for insight in account.get_api_insights():
                create_facebook_ads(account, insight)

            account.last_sync = date.today()
            account.save()

        stdout.write(' * API Call error: {}'.format(repr(e)))

    except Exception, e:
        raven_client.captureException()

        stdout.write(' * Error: {}'.format(repr(e)))


class Command(DropifiedBaseCommand):
    help = 'Sync Aliexpress fulfillment costs from last month'

    def add_arguments(self, parser):
        parser.add_argument('--progress', dest='progress', action='store_true', help='Show Progress')

    def start_command(self, *args, **options):
        progress = options['progress']

        self.q = Queue()
        for i in range(4):
            t = Thread(target=worker, args=(self.q, ))
            t.daemon = True
            t.start()

        facebook_access_list = FacebookAccess.objects.filter(expires_in__gt=timezone.now())
        count = facebook_access_list.count()
        if progress:
            obar = tqdm(total=count)

        start = 0

        for access in facebook_access_list:
            for account in access.accounts.all():
                self.q.put({
                    'account': account,
                    'stdout': self.stdout,
                })

            self.q.join()

            start += 1
            if progress:
                obar.update(1)

        if progress:
            obar.close()

        self.q.join()
