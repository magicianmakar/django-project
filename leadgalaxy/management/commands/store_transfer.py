from django.contrib.auth.models import User

import re

from shopified_core.utils import safe_int
from shopify_orders.models import ShopifyOrder
from leadgalaxy.utils import detach_webhooks
from leadgalaxy.models import (
    ShopifyStore,
    ShopifyProduct,
    ShopifyBoard,
    ShopifyOrderTrack
)

from shopified_core.commands import DropifiedBaseCommand


class Command(DropifiedBaseCommand):

    def add_arguments(self, parser):
        parser.add_argument(dest='store', type=str, help='Store shop link')
        parser.add_argument(dest='from', type=str, help='User that current have the store')
        parser.add_argument(dest='to', type=str, help='User to transfer ownership to')

        parser.add_argument('--permissions-check', dest='permissions_check', action='store_false',
                            help='Check if recipient have the store in his account')

        parser.add_argument('--dry-run', action='store_true',
                            help='Check if recipient have the store in his account')

    def start_command(self, *args, **options):
        from_user = User.objects.get(id=options['from']) if safe_int(options['from']) else User.objects.get(email__iexact=options['from'])
        to_user = User.objects.get(id=options['to']) if safe_int(options['to']) else User.objects.get(email__iexact=options['to'])

        shop = re.findall(r'[^/@\.]+\.myshopify\.com', options['store'])
        if not shop:
            self.write('Store {} not found'.format(shop))
            return
        else:
            shop = shop.pop()

        try:
            store = ShopifyStore.objects.get(shop=shop, user=from_user, is_active=True)
        except ShopifyStore.DoesNotExist:
            self.write('Store is not found on {} account'.format(from_user.email))
            return

        if not ShopifyStore.objects.filter(shop=shop, user=to_user).count():
            if options['permissions_check']:
                try:
                    store_info = store.get_info
                except:
                    store_info = {'email': ''}

                if store_info['email'].lower() == to_user.email.lower():
                    self.write('Warning: Store is not install on {} account but user email does match with Shopify Store email'.format(to_user.email))
                else:
                    self.write('Store {} is not install on {} account'.format(shop, to_user.email))
                    return
            else:
                self.write('Warning: Store is not install on {} account'.format(to_user.email))
        elif not options['dry_run']:
            for old_store in ShopifyStore.objects.filter(shop=shop, user=to_user, is_active=True):
                self.write('Disable {} on {} account'.format(old_store.shop, to_user.email))

                detach_webhooks(old_store, delete_too=True)

                old_store.is_active = False
                old_store.save()

        if not options['dry_run']:
            store.user = to_user
            store.save()

            self.write('ShopifyProduct...')
            ShopifyProduct.objects.filter(store=store, user=from_user).update(user=to_user)

            self.write('ShopifyOrderTrack...')
            ShopifyOrderTrack.objects.filter(store=store, user=from_user).update(user=to_user)

            self.write('ShopifyOrder...')
            ShopifyOrder.objects.filter(store=store, user=from_user).update(user=to_user)  # TODO: Elastic update

            self.write('ShopifyBoard...')
            ShopifyBoard.objects.filter(user=from_user).update(user=to_user)

            self.write('Store {} has been transferred to {} account'.format(store.shop, to_user.email))
        else:
            self.write(f'ShopifyProduct: {ShopifyProduct.objects.filter(store=store, user=from_user)}')
            self.write(f'ShopifyOrderTrack: {ShopifyOrderTrack.objects.filter(store=store, user=from_user)}')
            self.write(f'ShopifyOrder: {ShopifyOrder.objects.filter(store=store, user=from_user)}')
            self.write(f'ShopifyBoard: {ShopifyBoard.objects.filter(user=from_user)}')
