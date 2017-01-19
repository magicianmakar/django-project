import simplejson as json
from mock import patch, Mock
from django.utils import timezone

from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core import mail

from leadgalaxy import utils
from leadgalaxy.models import AliexpressProductChange
from product_alerts.management.commands.send_alerts import Command

import factory

ALERT_FREQUENCY = 24 # 24 hours for testing purpose.

class SendProductAlertsTestCase(TransactionTestCase):
    fixtures = ['product_changes.json']

    def setUp(self):
        self.user = User.objects.get(pk=1)

        self.changes = AliexpressProductChange.objects.all()

    @patch('leadgalaxy.utils.send_email_from_template', Mock())
    @patch('product_alerts.management.commands.send_alerts.Command.handle_changes')
    def test_notification_not_sent_for_changes_out_of_last_timespan(self, handle_changes):
        self.changes.update(created_at=(timezone.now() - timezone.timedelta(minutes=(60*ALERT_FREQUENCY + 1))))

        call_command('send_alerts', frequency=ALERT_FREQUENCY)

        handle_changes.assert_not_called()

    @patch('leadgalaxy.utils.send_email_from_template', Mock())
    @patch('product_alerts.management.commands.send_alerts.Command.handle_changes')
    def test_notification_sent_once_per_each_affected_user(self, handle_changes):
        affected_users = list(set([change.user for change in self.changes]))
        self.assertTrue(len(affected_users) == 1)
        self.assertEqual(affected_users, [self.user])

        self.changes.update(created_at=(timezone.now() - timezone.timedelta(minutes=(60*ALERT_FREQUENCY - 1))))

        call_command('send_alerts', frequency=ALERT_FREQUENCY)

        handle_changes.assert_called_once_with(self.user, [c for c in self.changes])

    @patch('leadgalaxy.utils.send_email_from_template', Mock())
    @patch('product_alerts.management.commands.send_alerts.Command.send_email')
    def test_notification_sent_with_changes_as_batch(self, send_email):
        command = Command()
        changes_map = command.handle_changes(self.user, [c for c in self.changes])

        # check if length of changes dict has 4 specified keys in total.
        self.assertEqual(len(changes_map), 4)
        self.assertIn('availability', changes_map)
        self.assertIn('price', changes_map)
        self.assertIn('quantity', changes_map)
        self.assertIn('removed', changes_map)

        # check if total number of availability changes is correct.
        self.assertEqual(len(changes_map['availability']), 3)
        # check if total number of disappeared products is correct.
        self.assertEqual(len([c for c in changes_map['availability'] if c['to'] == 'Offline']), 2)
        # check if total number of newly appeared products is correct.
        self.assertEqual(len([c for c in changes_map['availability'] if c['to'] == 'Online']), 1)

        # check if total number of variant price changes is correct.
        self.assertEqual(len([c for c in changes_map['price']]), 2)

        # check if total number of variant price changes is correct.
        self.assertEqual(len([c for c in changes_map['quantity']]), 3)

        # check if total number of variant removed changes is correct.
        self.assertEqual(len([c for c in changes_map['removed']]), 3)

        self.changes.update(created_at=(timezone.now() - timezone.timedelta(minutes=(60*ALERT_FREQUENCY - 1))))
        call_command('send_alerts', frequency=ALERT_FREQUENCY)

        # check if email is sent with computed batch data.
        send_email.assert_called_with(self.user, changes_map)
