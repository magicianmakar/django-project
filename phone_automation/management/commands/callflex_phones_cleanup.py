from datetime import timedelta
from django.utils import timezone
from raven.contrib.django.raven_compat.models import client as raven_client
import arrow
from phone_automation.models import TwilioPhoneNumber
from phone_automation.utils import get_twilio_client
from shopified_core.management import DropifiedBaseCommand


class Command(DropifiedBaseCommand):
    help = 'Cleanup unused phone numbers'

    def add_arguments(self, parser):
        parser.add_argument(
            '-u_id',
            '--user_id',
            default=False,
            help='Process only specified user'
        )
        parser.add_argument(
            '-preview_only',
            '--preview_only',
            default=False,
            help='Only preview phones to delete'
        )

    def start_command(self, *args, **options):
        # wait for launch date
        if arrow.utcnow() < arrow.get('2019-09-04'):
            self.write(f"Launch date not reached yet")
            return

        # Deleting phone which passed 90+14 days inactivity
        exp_date = timezone.now() + timedelta(days=-104)
        user_phones = TwilioPhoneNumber.objects
        if options['user_id']:
            user_phones = user_phones.filter(user_id=options['user_id'])

        for user_phone in user_phones.filter(created_at__lte=exp_date).iterator():

            try:
                self.write(f"Processing Twilio Phone Number {user_phone.pk} {user_phone.incoming_number} "
                           f" (user_id: {user_phone.user_id})")
                # checking latest call log

                latest_logs_count = user_phone.user.twilio_logs.filter(created_at__gte=exp_date).\
                    filter(twilio_metadata__To=user_phone.incoming_number).count()

                if latest_logs_count <= 0:
                    self.write(f"No call logs after {exp_date} Unregistering phone number")
                    if options['preview_only']:
                        self.write(f"Preview mode - phone wasn't deleted")
                    else:
                        client = get_twilio_client()
                        client.incoming_phone_numbers(user_phone.twilio_sid).delete()
                        user_phone.delete()
                        self.write(f"Phone {user_phone.twilio_sid} was deleted")
            except:
                raven_client.captureException()
