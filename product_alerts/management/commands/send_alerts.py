from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User

from leadgalaxy.models import AliexpressProductChange
from leadgalaxy.utils import send_email_from_template, get_variant_name, get_shopify_product
import simplejson as json
from django.utils import timezone

from raven.contrib.django.raven_compat.models import client as raven_client

STATIC_URL_BASE = 'http://dev.shopifiedapp.com/static/'
PRODUCT_URL_BASE = 'http://dev.shopifiedapp.com/product'

if not settings.DEBUG:
    STATIC_URL_BASE = 'https:{}'.format(settings.STATIC_URL)
    PRODUCT_URL_BASE = 'https://app.shopifiedapp.com/product'


class Command(BaseCommand):
    help = 'Send product change alerts per every given hours'

    def add_arguments(self, parser):
        parser.add_argument('-f',
                            '--frequency',
                            dest='frequency',
                            default=24,
                            help='Given a frequency, in hours, send product change alerts via email'
                            )

    def handle(self, *args, **options):
        try:
            self.start_command(*args, **options)
        except:
            raven_client.captureException()

    def start_command(self, *args, **options):
        frequency = int(options['frequency'])

        now = timezone.now()
        earlier = now - timezone.timedelta(hours=frequency)
        all_changes = AliexpressProductChange.objects.filter(created_at__range=(earlier, now))
        changes_by_user = {}

        for c in all_changes:
            if c.user_id not in changes_by_user:
                changes_by_user[c.user_id] = []
            changes_by_user[c.user_id].append(c)

        for user_id, changes in changes_by_user.items():
            try:
                user = User.objects.get(pk=user_id)
                self.handle_changes(user, changes)

            except User.DoesNotExist:
                raise CommandError('User "%s" does not exist' % user_id)

    def handle_changes(self, user, changes):
        changes_map = {'availability': [], 'price': [], 'quantity': [], 'removed': []}

        for change in changes:
            config = {
                'product_disappears': self.get_config('alert_product_disappears', change.product, user),
                'variant_disappears': self.get_config('alert_variant_disappears', change.product, user),
                'quantity_change': self.get_config('alert_quantity_change', change.product, user),
                'price_change': self.get_config('alert_price_change', change.product, user),
            }
            common_data = {
                'image': change.product.get_images()[0],  # self.get_shopify_product_image(change.product),
                'title': change.product.title,
                'url': '{}/{}'.format(PRODUCT_URL_BASE, change.product.id),
                'shopify_url': change.product.store.get_link('/admin/products/{}'.format(change.product.get_shopify_id())),
                'open_orders': change.orders_count()
            }
            events = json.loads(change.data)
            product_changes = events['changes']['product']
            variants_changes = []
            if 'variants' in events['changes']:
                variants_changes = events['changes']['variants']

            for product_change in product_changes:
                if product_change['category'] == 'Vendor' and config['product_disappears'] == 'notify':
                    availability = "Online" if not product_change['new_value'] else "Offline"
                    changes_map['availability'].append(dict({
                        'from': 'Offline' if availability == 'Online' else 'Online',
                        'to': availability
                    }, **common_data))

            new_prices = []
            old_prices = []
            new_quantities = []
            old_quantities = []
            removed_variants = []

            for variant in variants_changes:
                variant_name = get_variant_name(variant)

                for vc in variant['changes']:
                    if vc['category'] == 'removed':
                        removed_variants.append(variant_name)

                    elif vc['category'] == 'Price':
                        new_prices.append(vc['new_value'])
                        old_prices.append(vc['old_value'])

                    elif vc['category'] == 'Availability':
                        new_quantities.append(vc['new_value'])
                        old_quantities.append(vc['old_value'])

            if config['variant_disappears'] == 'notify' and len(removed_variants):
                changes_map['removed'].append(dict({
                    'variants': removed_variants
                }, **common_data))

            if config['price_change'] == 'notify':
                new_prices = list(set(new_prices))
                old_prices = list(set(old_prices))
                if len(new_prices):
                    changes_map['price'].append(dict({
                        'from': '${}'.format(old_prices[0]) if len(old_prices) == 1 else '${} -> ${}'.format(min(old_prices), max(old_prices)),
                        'to': '${}'.format(new_prices[0]) if len(new_prices) == 1 else '${} -> ${}'.format(min(new_prices), max(new_prices)),
                        'increase': max(new_prices) > max(old_prices)
                    }, **common_data))

            if config['quantity_change'] == 'notify':
                new_quantities = list(set(new_quantities))
                old_quantities = list(set(old_quantities))
                if len(new_quantities):
                    changes_map['quantity'].append(dict({
                        'from': '{}'.format(old_quantities[0]) if len(old_quantities) == 1 else '{} -> {}'.format(
                            min(old_quantities),
                            max(old_quantities)
                        ),
                        'to': '{}'.format(new_quantities[0]) if len(new_quantities) == 1 else '{} -> {}'.format(
                            min(new_quantities),
                            max(new_quantities)
                        ),
                        'increase': max(new_quantities) > max(old_quantities)
                    }, **common_data))

        # send changes_map to email template
        data = {
            'username': user.username,
            'changes_map': changes_map,
            'static_url_base': STATIC_URL_BASE
        }
        send_email_from_template(
            'product_change_notify.html',
            '[Shopified App] AliExpress Product Alert',
            user.email,
            data,
            nl2br=False
        )

    def get_config(self, name, product, user, default='notify'):
        value = product.get_config().get(name)
        if value is None:
            value = user.get_config(name, default)

        return value

    def get_shopify_product_image(self, product):
        shopify_product = get_shopify_product(product.store, product.get_shopify_id())
        if shopify_product:
            image = shopify_product.get('image')
            if image and type(image) is dict:
                return image.get('src')

        return None
