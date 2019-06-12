from raven.contrib.django.raven_compat.models import client as raven_client

from phone_automation.models import TwilioLog
from shopified_core.management import DropifiedBaseCommand


class Command(DropifiedBaseCommand):
    help = 'Fix old Callflex logs to be jsonable (for filtering)'

    def start_command(self, *args, **options):

        twilio_logs = TwilioLog.objects.iterator()
        for twilio_log in twilio_logs:
            try:
                self.write(f"Processing Twilio Log {twilio_log.pk} ")
                twilio_log.twilio_metadata = twilio_log.twilio_metadata_json
                twilio_log.save()
                self.write(twilio_log.twilio_metadata['To'] + " Json check passed")
            except:
                self.stderr.write(" Json check failed!")
                raven_client.captureException()
