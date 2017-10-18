import simplejson as json
import requests
from requests.auth import HTTPBasicAuth

from django.core.management.base import CommandError
from django.contrib.auth.models import User

from shopified_core.management import DropifiedBaseCommand
from shopified_core.utils import app_link
from leadgalaxy.models import *
from commercehq_core.models import CommerceHQProduct


from raven.contrib.django.raven_compat.models import client as raven_client

PRICE_MONITOR_BASE = '{}/api'.format(settings.PRICE_MONITOR_HOSTNAME)


class Command(DropifiedBaseCommand):
    help = 'Add products to be monitored'

    def add_arguments(self, parser):
        parser.add_argument('action', nargs=1, type=str,
                            choices=['attach', 'detach'], help='Action')
        parser.add_argument('store_type', nargs=1, type=str,
                            choices=['shopify', 'chq'], help='Store Type')

        parser.add_argument('--new', dest='new_products', action='store_true', help='Only New Products')
        parser.add_argument('--plan', dest='plan_id', action='append', type=int, help='Plan ID')
        parser.add_argument('--user', dest='user_id', action='append', type=int, help='User ID')
        parser.add_argument('--permission', dest='permission', action='append', type=str, help='Users with permission')

    def start_command(self, *args, **options):
        self.ignored_users = [16088, 10052, 10889, 13366, 8869, 6680, 8699, 11765, 14651, 12755, 10142, 14970]

        action = options['action'][0]
        store_type = options['store_type'][0]

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
                    if store_type == 'shopify':
                        self.handle_products(profile.user, profile.user.shopifyproduct_set.all(), action, options)
                    if store_type == 'chq':
                        self.handle_products(profile.user, profile.user.commercehqproduct_set.all(), action, options)

            except GroupPlan.DoesNotExist:
                raise CommandError('Plan "%s" does not exist' % plan_id)

        for permission in options['permission']:
            for p in AppPermission.objects.filter(name=permission):
                for plan in p.groupplan_set.all():
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

    def handle_products(self, user, products, action, options):
        if options['new_products']:
            products = products.filter(monitor_id=0)
        if products.model.__name__ == 'ShopifyProduct':
            products = products.exclude(shopify_id=0).exclude(store=None)
        if products.model.__name__ == 'CommerceHQProduct':
            products = products.exclude(source_id=0).exclude(store=None)

        products_count = len(products)

        if products_count:
            if user.id in self.ignored_users:
                self.stdout.write(u'Ignore {} product for user: {}'.format(products_count, user.username))

                products.update(monitor_id=-7)
                return

            self.stdout.write(u'{} webhooks to {} product for user: {}'.format(
                action.title(), products_count, user.username), self.style.HTTP_INFO)

            count = 0

            for product in products:
                self.handle_product(product, action)
                count += 1

                if (count % 100 == 0):
                    self.stdout.write(self.style.HTTP_INFO('Progress: %d' % count))

    def handle_product(self, product, action):
        if product.monitor_id:
            self.stdout.write(self.style.HTTP_INFO('Ignore, already registered.'))
            return

        try:
            supplier = product.default_supplier

            if 'aliexpress.com' not in supplier.product_url.lower():
                #  Not connected or not an Aliexpress product
                product.monitor_id = -1
                product.save()
                return

            store_id = supplier.get_store_id()
            if not store_id:
                store_id = 0

            product_id = supplier.get_source_id()
            if not product_id:
                # Product doesn't have Source Product ID
                product.monitor_id = -3
                product.save()
                return
        except:
            product.monitor_id = -5
            product.save()
            return

        self.attach_product(product, product_id, store_id)

    def attach_product(self, product, product_id, store_id):
        """
        product_id: Source Product ID (ex. Aliexpress ID)
        store_id: Source Store ID (ex. Aliexpress Store ID)
        """
        if product.__class__.__name__ == 'ShopifyProduct':
            dropified_type = 'shopify'
        if product.__class__.__name__ == 'CommerceHQProduct':
            dropified_type = 'chq'
        webhook_url = app_link('webhook/price-monitor/product', product=product.id, dropified_type=dropified_type)
        monitor_api_url = '{}/products'.format(PRICE_MONITOR_BASE)

        try:
            product_json = json.loads(product.data)
            post_data = {
                'product_id': product_id,
                'store_id': store_id,
                'dropified_id': product.id,
                'dropified_type': dropified_type,
                'dropified_store': product.store_id,
                'dropified_user': product.user_id,
                'webhook': webhook_url,
                'url': product.default_supplier.product_url,
            }
            # if product is variant-splitted product, pass its value.
            if product_json.get('variants_sku') and len(product_json['variants_sku']) == 1:
                post_data['variant_value'] = product_json['variants_sku'].values()[0]
            rep = requests.post(
                url=monitor_api_url,
                data=post_data,
                auth=HTTPBasicAuth(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD)
            )
        except Exception as e:
            raven_client.captureException()
            self.stdout.write(self.style.ERROR(' * API Call error: {}'.format(repr(e))))
            return

        try:
            assert rep.status_code == 200 or rep.status_code == 201, 'API Status Code'
            data = rep.json()
            product.monitor_id = data['id']
            product.save()
        except Exception as e:
            raven_client.captureException()
            self.stdout.write(self.style.ERROR(' * Attach Product ({}) Exception: {} \nResponse: {}'.format(
                product.id, repr(e), rep.text)))

            return
