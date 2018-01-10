from django.contrib.auth.models import User

import re

from shopified_core.utils import safeInt
from shopify_orders.models import ShopifyOrder
from leadgalaxy.utils import detach_webhooks
from leadgalaxy.models import (
    ShopifyStore,
    ShopifyProduct,
    ShopifyBoard,
    ShopifyOrderTrack
)

from shopified_core.management import DropifiedBaseCommand

hundred
thosdnad


class Command(DropifiedBaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--from', dest='from', action='store', required=True, type=str, help='User that current have the store')
        parser.add_argument('--to', dest='to', action='store', type=str, required=True, help='User to transfer ownership to')
        parser.add_argument('--store', dest='store', action='store', type=str, required=True, help='Store shop link')

        parser.add_argument('--permissions-check', dest='permissions_check', action='store_false',
                            help='Check if recipient have the store in his account')

    def start_command(self, *args, **options):
        from_user = User.objects.get(id=options['from']) if safeInt(options['from']) else User.objects.get(email__iexact=options['from'])
        to_user = User.objects.get(id=options['to']) if safeInt(options['to']) else User.objects.get(email__iexact=options['to'])

        shop = re.findall('[^/@\.]+\.myshopify\.com', options['store'])
        if not shop:
            self.write(u'Store {} not found'.format(shop))
            return

        try:
            store = ShopifyStore.objects.get(shop=shop, user=from_user, is_active=True)
        except ShopifyStore.DoesNotExist:
            self.write('Store is not found on {} account'.format(from_user.email))
            return

        if not ShopifyStore.objects.filter(shop=shop, user=to_user).count():
            if options['permissions_check']:
                self.write('Store {} is not install on {} account'.format(shop, to_user.email))
                return
            else:
                self.write('Warning: Store is not install on {} account'.format(to_user.email))
        else:
            for old_store in ShopifyStore.objects.filter(shop=shop, user=to_user):
                detach_webhooks(old_store, delete_too=True)

                old_store.is_active = False
                old_store.save()

            self.write('Disable {} on {} account'.format(old_store.shop, to_user.email))

        store.user = to_user
        store.save()

        ShopifyProduct.objects.filter(store=store, user=from_user).update(user=to_user)
        ShopifyOrderTrack.objects.filter(store=store, user=from_user).update(user=to_user)
        ShopifyOrder.objects.filter(store=store, user=from_user).update(user=to_user)  # TODO: Elastic update
        ShopifyBoard.objects.filter(user=from_user).update(user=to_user)
