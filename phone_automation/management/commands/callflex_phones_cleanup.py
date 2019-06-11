from datetime import timedelta

from django.utils import timezone

from raven.contrib.django.raven_compat.models import client as raven_client

from phone_automation.models import TwilioPhoneNumber
from phone_automation.utils import get_twilio_client
from shopified_core.management import DropifiedBaseCommand


class Command(DropifiedBaseCommand):
    help = 'Update Callflex Overages'

    def add_arguments(self, parser):
        parser.add_argument(
            '-u_id',
            '--user_id',
            default=False,
            help='Process only specified user'
        )

    def start_command(self, *args, **options):
        user_phones = TwilioPhoneNumber.objects
        if options['user_id']:
            user_phones = user_phones.filter(user_id=options['user_id'])

        for user_phone in user_phones.all():

            try:
                self.write(f"Processing Twilio Phone Number {user_phone.pk} (user_id: {user_phone.user_id})")
                # checking latest call log
                exp_date = timezone.now() + timedelta(days=-90)
                latest_logs_count = user_phone.twilio_logs.filter(created_at__gte=exp_date).count()
                if latest_logs_count <= 0:
                    self.write(f"No call logs after {exp_date} Unregistering phone number")
                    client = get_twilio_client()
                    client.incoming_phone_numbers(user_phone.twilio_sid).delete()
                    user_phone.delete()
            except:
                raven_client.captureException()
