from datetime import datetime

from django.db.models import Sum
from django.conf import settings

from twilio.rest import Client


def get_month_totals(user):
    date_start = datetime.today().replace(day=1)

    month_total_duration = user.twilio_logs.filter(
        log_type='status-callback'
    ).order_by('-created_at').filter(
        created_at__gte=date_start
    ).aggregate(Sum('call_duration'))

    return month_total_duration['call_duration__sum']


def get_month_limit(user):
    if user.can('phone_automation_unlimited_calls.use'):
        limit = False
    else:
        limit = int(settings.PHONE_AUTOMATION_MONTH_LIMIT)
    return limit


def get_twilio_client():
    return Client(settings.TWILIO_SID, settings.TWILIO_TOKEN)
