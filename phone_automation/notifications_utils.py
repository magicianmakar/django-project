from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Sum

from shopified_core.utils import safe_int
from shopified_core.utils import send_email_from_template

from typing import Dict
from .models import TwilioPhoneNumber, TwilioLog, TwilioAlert, TwilioSummary


class AlertNotification:

    def __init__(self, twilio_phone_number, twilio_log):
        # type: (TwilioPhoneNumber, TwilioLog) -> ...
        self.twilio_phone_number = twilio_phone_number
        self.twilio_log = twilio_log

    def process_alerts(self):
        # getting alerts assigned to a phone
        alerts_phone = self.twilio_phone_number.twilio_alerts.all()
        for alert in alerts_phone:
            self.process_alert(alert)

        # getting alerts assigned to entire phone's company (where selected 'All Phones')
        alerts_compnay = self.twilio_phone_number.company.twilio_alerts.filter(twilio_phone_number=None)
        for alert in alerts_compnay:
            self.process_alert(alert)
        return True

    def process_alert(self, twilio_alert):
        # type: (TwilioAlert ) -> ...

        if self.check_alert_trigger(twilio_alert):
            # getting company's users
            company_users = self.twilio_phone_number.company.get_config_users()
            alert_selected_users = twilio_alert.get_config_users()

            for company_user in company_users:
                if company_user in alert_selected_users:
                    self.send_notification(twilio_alert, company_user)
            return True
        else:
            return False

    def check_alert_trigger(self, twilio_alert):
        # type: (TwilioAlert ) -> ...

        if twilio_alert.alert_event == 'all_calls':
            return True
        if twilio_alert.alert_event == 'new_callers':
            user = twilio_alert.user
            twilio_logs_count = user.twilio_logs.filter(from_number=self.twilio_log.from_number).count()
            if twilio_logs_count > 1:
                return True
        if twilio_alert.alert_event == 'missed_calls' and self.twilio_log.call_status == 'no-answer':
            return True
        if twilio_alert.alert_event == 'voicemails' and self.twilio_log.twilio_recordings.exists():
            return True

        return False

    def send_notification(self, twilio_alert, company_user):
        # type: (TwilioAlert, Dict ) -> ...

        if twilio_alert.alert_type == 'email':
            # sending email

            send_email_from_template(
                tpl='callflex_alert.html',
                subject='CallFlex Notification',
                recipient=company_user['email'],
                data={
                    'twilio_alert': twilio_alert,
                    'company_user': company_user,
                    'twilio_log': self.twilio_log
                }
            )

            return True
        else:
            return False


class SummaryNotification:

    def __init__(self, twilio_summary):
        # type: (TwilioSummary) -> ...
        self.twilio_summary = twilio_summary
        self.from_date = None
        self.to_date = None

    def process_process_daily(self):
        # getting daily stats
        today = timezone.now().replace(hour=12, minute=0, second=0)
        yesterday = today - timedelta(1)
        self.from_date = yesterday
        self.to_date = today
        twilio_phone_numbers_stats = self.get_stats(self.from_date, self.to_date)
        company_users = self.twilio_summary.company.get_config_users()
        alert_selected_users = self.twilio_summary.get_config_users()
        for company_user in company_users:
            if company_user in alert_selected_users:
                self.send_notification(twilio_phone_numbers_stats, company_user)
        return True

    def process_process_weekly(self):
        # getting daily stats
        week_day = datetime.today().weekday()
        last_monday = timezone.now() + timedelta(days=(-week_day))
        last_monday = last_monday.replace(hour=12, minute=0, second=0)
        prev_monday = timezone.now() + timedelta(days=-(7 + week_day))
        prev_monday = prev_monday.replace(hour=12, minute=0, second=0)
        self.from_date = prev_monday
        self.to_date = last_monday
        twilio_phone_numbers_stats = self.get_stats(self.from_date, self.to_date)
        company_users = self.twilio_summary.company.get_config_users()
        alert_selected_users = self.twilio_summary.get_config_users()
        for company_user in company_users:
            if company_user in alert_selected_users:
                self.send_notification(twilio_phone_numbers_stats, company_user)
        return True

    def process_process_monthly(self):
        # getting daily stats
        last_month_start = timezone.now().replace(day=1, hour=12, minute=0, second=0)
        prev_month_start = (last_month_start + timedelta(days=- 1)).replace(day=1, hour=12, minute=0, second=0)
        self.from_date = prev_month_start
        self.to_date = last_month_start
        twilio_phone_numbers_stats = self.get_stats(self.from_date, self.to_date)
        company_users = self.twilio_summary.company.get_config_users()
        alert_selected_users = self.twilio_summary.get_config_users()
        for company_user in company_users:
            if company_user in alert_selected_users:
                self.send_notification(twilio_phone_numbers_stats, company_user)
        return True

    def get_stats(self, from_date, to_date):
        twilio_phone_numbers = self.twilio_summary.company.phones.all()

        for twilio_phone_number in twilio_phone_numbers:
            twilio_logs = twilio_phone_number.twilio_logs.filter(log_type='status-callback',
                                                                 created_at__gte=from_date,
                                                                 created_at__lte=to_date)
            stats = {}
            stats['total_calls'] = twilio_logs.count()
            stats['total_minutes'] = safe_int(twilio_logs.aggregate(Sum('call_duration'))['call_duration__sum'])
            twilio_phone_number.stats = stats
        return twilio_phone_numbers

    def send_notification(self, twilio_phone_numbers_stats, company_user):
        # sending email

        send_email_from_template(
            tpl='callflex_summary.html',
            subject='CallFlex Summary Report',
            recipient=company_user['email'],
            data={
                'twilio_phone_numbers': twilio_phone_numbers_stats,
                'company_user': company_user,
                'twilio_summary': self.twilio_summary,
                'from_date': self.from_date,
                'to_date': self.to_date,
            }
        )

        return True
