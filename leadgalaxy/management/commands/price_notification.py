from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db.models import Q

from leadgalaxy.models import *
from leadgalaxy import utils
import simplejson as json
import requests

from raven.contrib.django.raven_compat.models import client as raven_client

ALI_WEB_API_BASE = 'http://ali-web-api.herokuapp.com/api'
SHOPIFIEDAPP_WEBHOOK_BASE = 'http://app.shopifiedapp.com/webhook/price-notification/product'


class Command(BaseCommand):
    help = 'Attach Shopify Webhooks to a specific Plan'

    def add_arguments(self, parser):
        parser.add_argument('action', nargs=1, type=str,
                            choices=['attach', 'detach'], help='Action')

        parser.add_argument('--new', dest='new_products', action='store_true', help='Only New Products')
        parser.add_argument('--plan', dest='plan_id', action='append', type=int, help='Plan ID')
        parser.add_argument('--user', dest='user_id', action='append', type=int, help='User ID')
        parser.add_argument('--permission', dest='permission', action='append', type=str, help='Users with permission')

    def handle(self, *args, **options):
        try:
            self.start_command(*args, **options)
        except:
            raven_client.captureException()

    def start_command(self, *args, **options):
        action = options['action'][0]

        if not options['plan_id']:
            options['plan_id'] = []

        if not options['user_id']:
            options['user_id'] = []

        if not options['permission']:
            options['permission'] = []

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

    def handle_products(self, user, products, action, options):
        if options['new_products']:
            products = products.filter(price_notification_id=0)

        products_count = products.count()
        if products_count:
            self.stdout.write(self.style.HTTP_INFO('{} webhooks to {} product for user: {}'
                .format(action.title(), products_count, user.username)))

            count = 0

            for product in products:
                self.handle_product(product, action)
                count += 1

                if (count % 100 == 0):
                    self.stdout.write(self.style.HTTP_INFO('Progress: %d' % count))

    def handle_product(self, product, action):
        # print 'product {} Action {}'.format(product.id, action)

        data = json.loads(product.data)
        try:
            if product.price_notification_id:
                self.stdout.write(self.style.HTTP_INFO('Ignore, already registred.'))
                return

            origin = product.get_original_info()
            if not origin or 'aliexpress.com' not in origin.get('url').lower():
                # self.stdout.write(self.style.HTTP_INFO('Ignore, not connected or not Aliexpress product.'))
                product.price_notification_id = -1
                product.save()
                return

            try:
                store = data.get('store')
                store_id = store.get('url')
                store_id = int(re.findall('/([0-9]+)', store_id)[0])
            except Exception as e:
                product.price_notification_id = -2
                product.save()
                # self.stdout.write(self.style.ERROR(' * Product {} doesn\'t have Source Store ID'.format(product.id)))
                return

            product_id = product.get_source_id()
            if not product_id:
                raven_client.captureException()
                self.stdout.write(self.style.ERROR(' * Product {} doesn\'t have Source Product ID'.format(product.id)))
                return
        except Exception as e:
            raven_client.captureException()
            self.stdout.write(self.style.ERROR(' * Excpetion: {} - Product: {}'.format(repr(e), product.id)))
            return

        self.attach_product(product, product_id, store_id)

    def attach_product(self, product, product_id, store_id):
        """
        product_id: Source Product ID (ex. Aliexpress ID)
        store_id: Source Store ID (ex. Aliexpress Store ID)
        """

        webhook_url = '{}?product={}'.format(SHOPIFIEDAPP_WEBHOOK_BASE, product.id)
        notification_api_url = '{}/product/add'.format(ALI_WEB_API_BASE)

        try:
            rep = requests.post(
                url=notification_api_url,
                data={
                    'product_id': product_id,
                    'store_id': store_id,
                    'webhook': webhook_url,
                    'user_id': product.user_id
                }
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
            self.stdout.write(self.style.ERROR(' * Attach Product ({}) Exception: {} \nResponse: {}'.format(product.id, repr(e), rep.text)))
            return
