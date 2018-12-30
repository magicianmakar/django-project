import arrow
import pytz

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

    def get_users(self):
        """ Return users that will be notified

        Find users where time is (arround) 9:00 AM using the user's selected TimeZone in Profile page
        """
        users = []
        tz_list = []
        for tz in pytz.all_timezones_set:
            if arrow.now().to(tz).hour == 9:
                tz_list.append(tz)

                users.extend(User.objects.filter(profile__timezone=tz, profile__subuser_parent=None))

        self.write('Notfiy {} Users in {} Timezones'.format(len(users), len(tz_list)))

        return users

    def start_command(self, *args, **options):
        users = self.get_users()

        if not len(users):
            self.write('No user found to notify')
            return

        self.write('Notfiy changes for {} users'.format(len(users)))

        ignored_users = set()
        for user in users:
            prodduct_changes = ProductChange.objects.filter(user=user, notified_at=None, seen=False)

            last_notified_key = 'last_alert_id_{}'.format(user.id)
            last_notified_id = cache.get(last_notified_key, 30860000)

            prodduct_changes = prodduct_changes.filter(id__gt=last_notified_id)

            changes_list = list(prodduct_changes.order_by('-created_at')[:100])
            changes = changes_list[:20]

            if not changes:
                continue

            self.write('Notfiy {} about {} changes from {}'.format(user.email, len(changes_list), last_notified_id))

            notified_key = 'change_alert_{}'.format(user.id)
            if cache.get(notified_key):
                ignored_users.add(user)
                continue

            cache.set(last_notified_key, changes[0].id, timeout=86400 * 3)

            try:
                self.handle_changes(user, changes, len(changes_list))

                cache.set(notified_key, True, timeout=43200)

                ProductChange.objects.filter(id__in=[j.id for j in changes_list]).update(notified_at=timezone.now())

            except User.DoesNotExist:
                raven_client.captureException(level='warning')

            except:
                raven_client.captureException()

        if len(ignored_users):
            self.write('Notfiy {} ignored users'.format(len(ignored_users)))

    def handle_changes(self, user, changes, changes_count):
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

        self.send_email(user, changes_map, cc_list=cc_list, changes_count=changes_count)
        return changes_map

    def send_email(self, user, changes_map, cc_list=[], changes_count=None):
        # send changes_map to email template
        data = {
            'username': user.username,
            'changes_map': changes_map,
            'have_more_changes': changes_count,
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
