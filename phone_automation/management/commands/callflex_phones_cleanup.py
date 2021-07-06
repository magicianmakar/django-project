from datetime import timedelta

from django.utils import timezone
from django.db.models import Q

from lib.exceptions import capture_exception

from phone_automation.models import TwilioPhoneNumber
from shopified_core.commands import DropifiedBaseCommand


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

        # Deleting phone which marked for deletion and passed 30 days
        marked_user_phones = TwilioPhoneNumber.objects.filter(status='scheduled_deletion')
        if options['user_id']:
            marked_user_phones = marked_user_phones.filter(user_id=options['user_id'])
        for marked_user_phone in marked_user_phones.iterator():
            if marked_user_phone.removable:
                try:
                    self.write(f"Deleting marked phone {marked_user_phone}")
                    marked_user_phone.safe_delete()
                except:
                    capture_exception()

        # Deleting phone which passed 90+14 days inactivity
        exp_date = timezone.now() + timedelta(days=-104)
        # Never delete Dropified CS Number: +18443112873
        user_phones = TwilioPhoneNumber.objects.filter(~Q(incoming_number='+18443112873'))
        if options['user_id']:
            user_phones = user_phones.filter(user_id=options['user_id'])

        for user_phone in user_phones.filter(created_at__lte=exp_date).iterator():

            try:
                # checking latest call log

                latest_logs_count = user_phone.user.twilio_logs.filter(created_at__gte=exp_date).\
                    filter(twilio_metadata__To=user_phone.incoming_number).count()

                if latest_logs_count <= 0:
                    self.write(f"No call logs after {exp_date} Unregistering phone number")
                    if options['preview_only']:
                        self.write("Preview mode - phone wasn't deleted")
                    else:
                        user_phone.delete()
                        self.write(f"Phone {user_phone.twilio_sid} was deleted")
            except:
                capture_exception()
