from random import randint
from time import sleep

from tqdm import tqdm
from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.management import DropifiedBaseCommand
from profit_dashboard.models import FacebookAccess
from profit_dashboard.utils import get_facebook_ads


class Command(DropifiedBaseCommand):
    help = 'Sync Aliexpress fulfillment costs from last month'

    def add_arguments(self, parser):
        parser.add_argument('--noprogress', dest='progress', action='store_false',
                            help='Hide Progress')

        parser.add_argument('--times', dest='times', type=int, help='Run (n) times')

    def start_command(self, *args, **options):
        progress = options['progress']
        times = options.get('times') or 1
        count_times = 0

        facebook_access_list = FacebookAccess.objects.all()
        count = facebook_access_list.count() * times
        if progress:
            obar = tqdm(total=count)

        start = 0

        try:
            while count_times < times:
                for access in facebook_access_list:
                    get_facebook_ads(access.user,
                                     access.store,
                                     access.access_token,
                                     access.account_ids.split(','),
                                     access.campaigns.split(','))

                    sleep(randint(30, 60))  # Avoid hiting user calls limit
                    start += 1
                    if progress:
                        obar.update(1)

                count_times += 1

        except Exception as e:
            print e
            raven_client.captureException()

        if progress:
            obar.close()
