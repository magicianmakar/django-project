import arrow

from django.contrib.auth.models import User
from django.utils import timezone
from django.core.cache import cache

from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.management import DropifiedBaseCommand
from shopified_core.utils import send_email_from_template
from product_alerts.models import ProductChange
from product_alerts.managers import ProductChangeManager


class Command(DropifiedBaseCommand):
    help = 'Send product change alerts per every given hours'

    users_more_changes = {}

    def start_command(self, *args, **options):
        prodduct_changes = ProductChange.objects.filter(notified_at=None, created_at__gte=arrow.now().replace(days=-1).datetime).order_by('user_id')

        changes_user_map = {}

        for change in prodduct_changes:
            if change.user_id not in changes_user_map:
                changes_user_map[change.user_id] = []

            if len(changes_user_map[change.user_id]) <= 20:
                changes_user_map[change.user_id].append(change)
            else:
                self.users_more_changes[change.user_id] = self.users_more_changes.get(change.user_id, 0) + 1

        self.stdout.write('Notfiy {} changes for {} users'.format(len(prodduct_changes), len(changes_user_map)))
        self.stdout.write('Notfiy {}/{} extra changes'.format(len(self.users_more_changes), sum(self.users_more_changes.values())))

        ignored_users = set()
        for user_id, changes in changes_user_map.items():
            try:
                user = User.objects.get(pk=user_id)

                notified_key = 'change_alert_{}'.format(user.id)
                if cache.get(notified_key):
                    ignored_users.add(user)
                    continue

                self.handle_changes(user, changes)

                cache.set(notified_key, True, timeout=86400)

                ProductChange.objects.filter(id__in=[j.id for j in changes]).update(notified_at=timezone.now())

            except User.DoesNotExist:
                raven_client.captureException(level='warning')

            except:
                raven_client.captureException()

        if len(ignored_users):
            self.stdout.write('Notfiy {} ignored users'.format(len(ignored_users)))

    def handle_changes(self, user, changes):
        user_changes_map = {
            'availability': [],
            'price': [],
            'quantity': [],
            'removed': [],
            'added': [],
        }

        for change in changes:
            manager = ProductChangeManager.initialize(change)
            changes_map = manager.changes_map()
            for name, changes in changes_map.iteritems():
                if user_changes_map.get(name):
                    user_changes_map[name].extend(changes)

        cc_list = []
        if self.get_config('send_alerts_to_subusers', None, user, default=False):
            for sub_user in User.objects.filter(profile__subuser_parent=user):
                if sub_user.profile.subuser_stores.filter(is_active=True).count():
                    cc_list.append(sub_user.email)

        self.send_email(user, changes_map, cc_list=cc_list)
        return changes_map

    def send_email(self, user, changes_map, cc_list=[]):
        # send changes_map to email template
        data = {
            'username': user.username,
            'changes_map': changes_map,
            'have_more_changes': self.users_more_changes.get(user)
        }

        if any([changes_map['availability'],
                changes_map['price'],
                changes_map['quantity'],
                changes_map['removed'],
                changes_map['added']]):

            recipient_list = [user.email]
            if len(cc_list):
                recipient_list = recipient_list + cc_list

            send_email_from_template(
                'product_change_notify.html',
                '[Dropified] AliExpress Product Alert',
                recipient_list,
                data,
                from_email='"Dropified" <no-reply@dropified.com>'
            )

    def get_config(self, name, product, user, default='notify'):
        value = None

        if product:
            product.get_config().get(name)

        if value is None:
            value = user.get_config(name, default)

        return value
