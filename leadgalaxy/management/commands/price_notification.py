from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from leadgalaxy.models import *
from leadgalaxy import utils
import json
import requests


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

    def handle(self, *args, **options):
        action = options['action'][0]

        if not options['plan_id']:
            options['plan_id'] = []

        if not options['user_id']:
            options['user_id'] = []

        for plan_id in options['plan_id']:
            try:
                plan = GroupPlan.objects.get(pk=plan_id)
            except GroupPlan.DoesNotExist:
                raise CommandError('Plan "%s" does not exist' % plan_id)

            self.stdout.write(self.style.MIGRATE_SUCCESS(
                '{} webhooks for plan: {}'.format(action.title(), plan.title)))

            products = ShopifyProduct.objects.filter(user__profile__plan=plan)
            if options['new_products']:
                products = products.filter(price_notification_id=0)

            self.stdout.write(self.style.HTTP_INFO('Products count: %d' % products.count()))
            count = 0
            for product in products:
                self.handle_product(product, action)
                count += 1

                # if (count % 10 == 0):
                    # self.stdout.write(self.style.HTTP_INFO('Progress: %d' % count))

        for user_id in options['user_id']:
            try:
                user = User.objects.get(pk=user_id)
            except ShopifyStore.DoesNotExist:
                raise CommandError('User "%s" does not exist' % user_id)

            self.stdout.write(self.style.MIGRATE_SUCCESS(
                '{} webhooks for user: {}'.format(action.title(), user.username)))

            products = ShopifyProduct.objects.filter(user=user)
            self.stdout.write(self.style.HTTP_INFO('products count: %d' % products.count()))
            for product in products:
                self.handle_product(product, action)

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
                return

            try:
                store = data.get('store')
                store_id = store.get('url')
                store_id = int(re.findall('/([0-9]+)', store_id)[0])
            except Exception as e:
                # self.stdout.write(self.style.ERROR(' * Product {} doesn\'t have Source Store ID'.format(product.id)))
                return

            product_id = product.get_source_id()
            if not product_id:
                self.stdout.write(self.style.ERROR(' * Product {} doesn\'t have Source Product ID'.format(product.id)))
                return
        except Exception as e:
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
            self.stdout.write(self.style.ERROR(' * API Call error: {}'.format(repr(e))))
            return

        try:
            assert rep.status_code == 200, 'API Status Code'
            data = rep.json()

            assert data.get('status') == 'ok', 'API Reutrn OK'

            product.price_notification_id = data['id']
            product.save()
        except Exception as e:
            self.stdout.write(self.style.ERROR(' * Attach Product ({}) Exception: {} \nResponse: {}'.format(product.id, repr(e), rep.text)))
            return
