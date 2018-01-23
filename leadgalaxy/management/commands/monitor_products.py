from Queue import Queue
from threading import Thread

from django.core.management.base import CommandError
from django.contrib.auth.models import User
from django.db.models import Q

from shopified_core.management import DropifiedBaseCommand
from leadgalaxy.models import *
from commercehq_core.models import CommerceHQProduct
from product_alerts.utils import monitor_product


PRICE_MONITOR_BASE = '{}/api'.format(settings.PRICE_MONITOR_HOSTNAME)


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
        parser.add_argument('action', nargs=1, type=str,
                            choices=['attach', 'detach'], help='Action')
        parser.add_argument('store_type', nargs=1, type=str,
                            choices=['shopify', 'chq'], help='Store Type')

        parser.add_argument('--plan', dest='plan_id', action='append', type=int, help='Plan ID')
        parser.add_argument('--exclude-plan', dest='exclude_plan_id', action='append', type=int, help='Plan ID')
        parser.add_argument('--user', dest='user_id', action='append', type=int, help='User ID')
        parser.add_argument('--permission', dest='permission', action='append', type=str, help='Users with permission')

    def start_command(self, *args, **options):
        self.ignored_users = [16088, 10052, 10889, 13366, 8869, 6680, 8699, 11765, 14651, 12755, 10142, 14970]

        action = options['action'][0]
        store_type = options['store_type'][0]

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
                self.stdout.write(self.style.MIGRATE_SUCCESS(
                    '{} webhooks for Plan: {}'.format(action.title(), plan.title)))

                for profile in plan.userprofile_set.select_related('user').all():
                    if store_type == 'shopify':
                        self.handle_products(profile.user, profile.user.shopifyproduct_set.all(), action, options)
                    if store_type == 'chq':
                        self.handle_products(profile.user, profile.user.commercehqproduct_set.all(), action, options)

            except GroupPlan.DoesNotExist:
                raise CommandError('Plan "%s" does not exist' % plan_id)

        for permission in options['permission']:
            for p in AppPermission.objects.filter(name=permission):
                for plan in p.groupplan_set.all():
                    if plan.id in options['exclude_plan_id']:
                        self.stdout.write('* Ignore Plan: {}'.format(plan.title))
                        continue

                    self.stdout.write(self.style.MIGRATE_SUCCESS(
                        '{} webhooks for Plan: {}'.format(action.title(), plan.title)))

                    for profile in plan.userprofile_set.select_related('user').all():
                        if store_type == 'shopify':
                            self.handle_products(profile.user, profile.user.shopifyproduct_set.all(), action, options)
                        if store_type == 'chq':
                            self.handle_products(profile.user, profile.user.commercehqproduct_set.all(), action, options)

                for bundle in p.featurebundle_set.all():
                    self.stdout.write(self.style.MIGRATE_SUCCESS(
                        '{} webhooks for Bundle: {}'.format(action.title(), bundle.title)))
                    for profile in bundle.userprofile_set.select_related('user').all():
                        if store_type == 'shopify':
                            self.handle_products(profile.user, profile.user.shopifyproduct_set.all(), action, options)
                        if store_type == 'chq':
                            self.handle_products(profile.user, profile.user.commercehqproduct_set.all(), action, options)

        for user_id in options['user_id']:
            try:
                user = User.objects.get(pk=user_id)
                products = None
                if store_type == 'shopify':
                    products = ShopifyProduct.objects.filter(user=user)
                if store_type == 'chq':
                    products = CommerceHQProduct.objects.filter(user=user)
                self.handle_products(user, products, action, options)

            except User.DoesNotExist:
                raise CommandError('User "%s" does not exist' % user_id)

        self.q.join()

    def handle_products(self, user, products, action, options):
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
            if products_count > 1000:
                self.stdout.write(u'Too many products ({}) for user: {}'.format(products_count, user.username))
                return

            self.stdout.write(u'{} webhooks to {} product for user: {}'.format(
                action.title(), products_count, user.username), self.style.HTTP_INFO)

            for product in products:
                self.handle_product(product, action)

        self.q.join()

    def handle_product(self, product, action):
        if product.monitor_id:
            self.stdout.write(self.style.HTTP_INFO('Ignore, already registered.'))
            return

        self.q.put({
            'product': product,
            'stdout': self.stdout,
        })
