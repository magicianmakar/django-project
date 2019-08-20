from datetime import timedelta

from django.utils import timezone

from raven.contrib.django.raven_compat.models import client as raven_client
from shopified_core.utils import last_executed
from phone_automation.models import TwilioPhoneNumber
from shopified_core.management import DropifiedBaseCommand
from shopified_core.utils import send_email_from_template


class Command(DropifiedBaseCommand):
    help = 'Alert users about expiring phones (no calls during 87 days)'

    def add_arguments(self, parser):
        parser.add_argument(
            '-u_id',
            '--user_id',
            default=False,
            help='Process only specified user'
        )

    def start_command(self, *args, **options):
        exp_days_array = [14, 7, 3]
        total_users_notified = 0

        for exp_days_item in exp_days_array:
            exp_date = timezone.now() + timedelta(days=-(90 + 14 - exp_days_item))

            self.write(f"Fetching all till {exp_date} ")

            user_phones = TwilioPhoneNumber.objects
            if options['user_id']:
                user_phones = user_phones.filter(user_id=options['user_id'])

            for user_phone in user_phones.filter(created_at__lte=exp_date).iterator():

                try:
                    self.write(f"Processing Twilio Phone Number {user_phone.pk} {user_phone.incoming_number} "
                               f" (user_id: {user_phone.user_id})")
                    # checking latest call log

                    latest_logs_count = user_phone.user.twilio_logs.filter(created_at__gte=exp_date). \
                        filter(twilio_metadata__To=user_phone.incoming_number).count()

                    if latest_logs_count <= 0:
                        self.write(f"No call logs after {exp_date} Send email alert to {user_phone.user.email}")
                        if not last_executed(f'callflex_phone_{user_phone.id}_release_alert', 3600 * 24 * 4):
                            send_email_from_template(
                                tpl='callflex_phone_alert.html',
                                subject='CallFlex PhoneNumber Alert',
                                recipient=user_phone.user.email,
                                exp_days=exp_days_item,
                                data={
                                    'twilio_phone': user_phone,
                                    'user': user_phone.user
                                }
                            )
                            total_users_notified += 1
                        else:
                            self.write(f"No call logs after {exp_date} email already sent before")

                except:
                    raven_client.captureException()
        self.write(f"Total users notified: {total_users_notified} ")
