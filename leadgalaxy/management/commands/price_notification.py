from Queue import Queue
from threading import Thread

from django.core.management.base import CommandError
from django.contrib.auth.models import User

from shopified_core.management import DropifiedBaseCommand
from shopified_core.utils import app_link
from leadgalaxy.models import *

import simplejson as json
import requests

from raven.contrib.django.raven_compat.models import client as raven_client

ALI_WEB_API_BASE = 'http://ali-web-api.herokuapp.com/api'


def worker(q):
    while True:
        item = q.get()
        attach_product(**item)
        q.task_done()


def attach_product(product, product_id, store_id, stdout=None):
    """
    product: ShopifyProduct model instance
    product_id: Source Product ID (ex. Aliexpress ID)
    store_id: Source Store ID (ex. Aliexpress Store ID)
    """

    webhook_url = app_link('webhook/price-notification/product', product=product.id)
    notification_api_url = '{}/product/add'.format(ALI_WEB_API_BASE)

    try:
        product_json = json.loads(product.data)
        post_data = {
            'product_id': product_id,
            'store_id': store_id,
            'webhook': webhook_url,
            'user_id': product.user_id,
        }
        # if product is variant-splitted product, pass its value.
        if product_json.get('variants_sku') and len(product_json['variants_sku']) == 1:
            post_data['variant_value'] = product_json['variants_sku'].values()[0]
        rep = requests.post(
            url=notification_api_url,
            data=post_data
        )
    except Exception as e:
        raven_client.captureException()
        self.stdout.write(self.style.ERROR(' * API Call error: {}'.format(repr(e))))
        return

    try:
        assert rep.status_code == 200, 'API Status Code'
        data = rep.json()

        assert data.get('status') == 'ok', 'API Reutrn OK'

        product.price_notification_id = data['id']
        product.save()
    except Exception as e:
        raven_client.captureException()
        self.stdout.write(self.style.ERROR(' * Attach Product ({}) Exception: {} \nResponse: {}'.format(
            product.id, repr(e), rep.text)))


class Command(DropifiedBaseCommand):
    help = 'Attach Shopify Webhooks to a specific Plan'

    def add_arguments(self, parser):
        parser.add_argument('action', nargs=1, type=str,
                            choices=['attach', 'detach'], help='Action')

        parser.add_argument('--new', dest='new_products', action='store_true', help='Only New Products')
        parser.add_argument('--plan', dest='plan_id', action='append', type=int, help='Plan ID')
        parser.add_argument('--exclude-plan', dest='exclude_plan_id', action='append', type=int, help='Plan ID')
        parser.add_argument('--user', dest='user_id', action='append', type=int, help='User ID')
        parser.add_argument('--permission', dest='permission', action='append', type=str, help='Users with permission')

    def start_command(self, *args, **options):
        self.ignored_users = [16088, 10052, 10889, 13366, 8869, 6680, 8699, 11765, 14651, 12755, 10142, 14970, 13911]

        action = options['action'][0]

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
                    self.handle_products(profile.user, profile.user.shopifyproduct_set.all(), action, options)

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
                        self.handle_products(profile.user, profile.user.shopifyproduct_set.all(), action, options)

                for bundle in p.featurebundle_set.all():
                    self.stdout.write(self.style.MIGRATE_SUCCESS(
                        '{} webhooks for Bundle: {}'.format(action.title(), bundle.title)))
                    for profile in bundle.userprofile_set.select_related('user').all():
                        self.handle_products(profile.user, profile.user.shopifyproduct_set.all(), action, options)

        for user_id in options['user_id']:
            try:
                user = User.objects.get(pk=user_id)
                products = ShopifyProduct.objects.filter(user=user)
                self.handle_products(user, products, action, options)

            except ShopifyStore.DoesNotExist:
                raise CommandError('User "%s" does not exist' % user_id)

        self.q.join()

    def handle_products(self, user, products, action, options):
        if options['new_products']:
            products = products.filter(price_notification_id=0)

        products = products.exclude(shopify_id=0).exclude(store=None).exclude(store__is_active=False)

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
        if product.price_notification_id:
            self.stdout.write(self.style.HTTP_INFO('Ignore, already registred.'))
            return

        try:
            supplier = product.default_supplier

            if 'aliexpress.com' not in supplier.product_url.lower():
                #  Not connected or not an Aliexpress product
                product.price_notification_id = -1
                product.save()
                return

            store_id = supplier.get_store_id()
            if not store_id:
                store_id = 0

            product_id = supplier.get_source_id()
            if not product_id:
                # Product doesn't have Source Product ID
                product.price_notification_id = -3
                product.save()
                return
        except:
            product.price_notification_id = -5
            product.save()
            return

        self.q.put({
            'product': product,
            'product_id': product_id,
            'store_id': store_id,
            'stdout': self.stdout,
        })
