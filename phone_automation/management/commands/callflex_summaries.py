from raven.contrib.django.raven_compat.models import client as raven_client

import phone_automation.notifications_utils as notifications
from phone_automation.models import TwilioSummary
from shopified_core.management import DropifiedBaseCommand


class Command(DropifiedBaseCommand):
    help = 'Process Callflex summary reports'

    def start_command(self, *args, **options):
        twilio_summaries = TwilioSummary.objects.all()
        for twilio_summary in twilio_summaries:
            summary_notification = notifications.SummaryNotification(twilio_summary)

            try:
                if twilio_summary.freq_daily:
                    self.stdout.write('Processing daily summaries for summary ID:' + str(twilio_summary.id))
                    summary_notification.process_process_daily()
                if twilio_summary.freq_weekly:
                    self.stdout.write('Processing weekly summaries for summary ID:' + str(twilio_summary.id))
                    summary_notification.process_process_weekly()
                if twilio_summary.freq_monthly:
                    self.stdout.write('Processing monthly summaries for summary ID:' + str(twilio_summary.id))
                    summary_notification.process_process_monthly()
            except:
                raven_client.captureException()