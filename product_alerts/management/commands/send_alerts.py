import simplejson as json
import arrow

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from leadgalaxy.models import AliexpressProductChange
from leadgalaxy.utils import send_email_from_template, get_variant_name
from django.utils import timezone

from raven.contrib.django.raven_compat.models import client as raven_client


class Command(BaseCommand):
    help = 'Send product change alerts per every given hours'

    def handle(self, *args, **options):
        try:
            self.start_command(*args, **options)
        except:
            raven_client.captureException()

    def start_command(self, *args, **options):
        merge_date = arrow.get(1487693000).datetime  # Date when this change was deployed

        all_changes = AliexpressProductChange.objects.filter(created_at__gt=merge_date) \
                                                     .filter(notified_at=None) \
                                                     .order_by('user_id')

        changes_by_user = {}

        if options['verbosity'] > 1:
            self.stdout.write('Notfiy {} changes'.format(all_changes.count()))

        for c in all_changes:
            if c.user_id not in changes_by_user:
                changes_by_user[c.user_id] = []
            changes_by_user[c.user_id].append(c)

        for user_id, changes in changes_by_user.items():
            try:
                user = User.objects.get(pk=user_id)
                self.handle_changes(user, changes)

                AliexpressProductChange.objects.filter(id__in=[j.id for j in changes]) \
                                               .update(notified_at=timezone.now())

            except User.DoesNotExist:
                raven_client.captureException(level='warning')

            except:
                raven_client.captureException()

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
                'image': change.product.get_images()[0],
                'title': change.product.title,
                'url': 'https://app.shopifiedapp.com/product/{}'.format(change.product.id),
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
                    from_range = '${:.02f} - ${:.02f}'.format(min(old_prices), max(old_prices))
                    to_range = '${:.02f} - ${:.02f}'.format(min(new_prices), max(new_prices))

                    changes_map['price'].append(dict({
                        'from': '${:.02f}'.format(old_prices[0]) if len(old_prices) == 1 else from_range,
                        'to': '${:.02f}'.format(new_prices[0]) if len(new_prices) == 1 else to_range,
                        'increase': max(new_prices) > max(old_prices)
                    }, **common_data))

            if config['quantity_change'] == 'notify':
                new_quantities = list(set(new_quantities))
                old_quantities = list(set(old_quantities))
                if len(new_quantities):
                    changes_map['quantity'].append(dict({
                        'from': '{}'.format(old_quantities[0]) if len(old_quantities) == 1 else '{} - {}'.format(
                            min(old_quantities),
                            max(old_quantities)
                        ),
                        'to': '{}'.format(new_quantities[0]) if len(new_quantities) == 1 else '{} - {}'.format(
                            min(new_quantities),
                            max(new_quantities)
                        ),
                        'increase': max(new_quantities) > max(old_quantities)
                    }, **common_data))

        self.send_email(user, changes_map)
        return changes_map

    def send_email(self, user, changes_map):
        # send changes_map to email template
        data = {
            'username': user.username,
            'changes_map': changes_map,
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
