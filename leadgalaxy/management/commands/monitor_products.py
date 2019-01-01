from Queue import Queue
from threading import Thread

from django.core.management.base import CommandError
from django.contrib.auth.models import User
from django.db.models import Q

from shopified_core.management import DropifiedBaseCommand
from shopified_core.utils import url_join
from leadgalaxy.models import *
from commercehq_core.models import CommerceHQProduct
from product_alerts.utils import monitor_product
from last_seen.models import LastSeen


def worker(q):
    while True:
        item = q.get()
        attach_product(**item)
        q.task_done()


def attach_product(product, stdout=None):
    monitor_product(product, stdout)


class Command(DropifiedBaseCommand):
    help = 'Add products to be monitored'

    def add_arguments(self, parser):
        parser.add_argument('--plan', dest='plan_id', action='append', type=int, help='Plan ID')
        parser.add_argument('--exclude-plan', dest='exclude_plan_id', action='append', type=int, help='Plan ID')
        parser.add_argument('--user', dest='user_id', action='append', type=int, help='User ID')
        parser.add_argument('--permission', dest='permission', action='append', type=str, help='Users with permission')
        parser.add_argument('--remove-inactive', dest='remove-inactive', action='store_true', help='Remove products of inactive users')

    def start_command(self, *args, **options):
        self.ignored_users = [16088, 10052, 10889, 13366, 8869, 6680, 8699, 11765, 14651, 12755, 10142, 14970]

        if not options['plan_id']:
            options['plan_id'] = []

        if not options['exclude_plan_id']:
            options['exclude_plan_id'] = []

        if not options['user_id']:
            options['user_id'] = []

        if not options['permission']:
            options['permission'] = []

        self.q = Queue()
        for i in range(4):
            t = Thread(target=worker, args=(self.q, ))
            t.daemon = True
            t.start()

        for plan_id in options['plan_id']:
            try:
                plan = GroupPlan.objects.get(pk=plan_id)
                self.stdout.write(self.style.SUCCESS('Plan: {}'.format(plan.title)))

                for profile in plan.userprofile_set.select_related('user').all():
                    self.handle_user(profile.user, options)

            except GroupPlan.DoesNotExist:
                raise CommandError('Plan "%s" does not exist' % plan_id)

        for permission in options['permission']:
            for p in AppPermission.objects.filter(name=permission):
                for plan in p.groupplan_set.all():
                    if plan.id in options['exclude_plan_id']:
                        self.stdout.write('* Ignore Plan: {}'.format(plan.title))
                        continue

                    self.stdout.write(self.style.SUCCESS(u'Plan: {}'.format(plan.title)))

                    for profile in plan.userprofile_set.select_related('user').all():
                        self.handle_user(profile.user, options)

                for bundle in p.featurebundle_set.all():
                    self.stdout.write(self.style.SUCCESS(u'Bundle: {}'.format(bundle.title)))

                    for profile in bundle.userprofile_set.select_related('user').all():
                        self.handle_user(profile.user, options)

        for user_id in options['user_id']:
            try:
                user = User.objects.get(pk=user_id)
                self.handle_user(user, options)

            except User.DoesNotExist:
                raise CommandError('User "%s" does not exist' % user_id)

        self.q.join()

    def handle_user(self, user, options):
        try:
            LastSeen.objects.when(user, 'website')
        except LastSeen.DoesNotExist:
            self.stdout.write(u'Ignore inactive user: {}'.format(user.username))
            if options['remove-inactive']:
                rep = requests.delete(
                    url=url_join(settings.PRICE_MONITOR_HOSTNAME, '/api/products'),
                    params={'user': user.id},
                    auth=(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD)
                )

                rep.raise_for_status()

                if not rep.text.startswith('0 '):
                    self.write(u'\t{}'.format(rep.text))

            return

        self.handle_products(user, CommerceHQProduct.objects.filter(user=user))
        self.handle_products(user, ShopifyProduct.objects.filter(user=user))

    def handle_products(self, user, products):
        products = products.filter(Q(monitor_id=0) | Q(monitor_id=None))

        if products.model.__name__ == 'ShopifyProduct':
            products = products.exclude(shopify_id=0)
        elif products.model.__name__ == 'CommerceHQProduct':
            products = products.exclude(source_id=0)

        products = products.filter(store__is_active=True)

        if user.id in self.ignored_users:
            self.stdout.write(u'Ignore product for user: {}'.format(user.username))
            return

        products_count = products.count()

        if products_count:
            if products_count > 10000:
                self.stdout.write(u'Too many products ({}) for user: {}'.format(products_count, user.username))
                return

            self.stdout.write(u'Add {} products for user: {}'.format(products_count, user.username), self.style.HTTP_INFO)

            start = 0
            steps = 1000
            while start <= products_count:
                for product in products[start:start + steps]:
                    self.handle_product(product)

                start += steps

        self.q.join()

    def handle_product(self, product):
        if product.monitor_id:
            self.stdout.write(self.style.HTTP_INFO('Ignore, already registered.'))
            return

        self.q.put({
            'product': product,
            'stdout': self.stdout,
        })
