import arrow
import calendar
import json

from urllib.parse import urlsplit

import boto.elastictranscoder
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.postgres.fields import JSONField
from django.forms.models import model_to_dict
from django.utils.functional import cached_property
from django.urls import reverse
from .utils import (
    get_twilio_client,
)
from leadgalaxy.utils import aws_s3_get_key
from stripe_subscription.models import CustomStripeSubscription
from datetime import timedelta

PHONE_NUMBER_STATUSES = (
    ('active', 'Incoming calls allowed'),
    ('inactive', 'Forwardning all incoming calls'),
    ('released', 'Released'),
    ('scheduled_deletion', 'Scheduled for deletion'),
)

PHONE_NUMBER_TYPES = (
    ('tollfree', 'Toll-Free Number'),
    ('local', 'Local Number'),
)

ALERT_EVENTS = (
    ('all_calls', 'All Calls'),
    ('new_callers', 'Only First Time Callers'),
    ('missed_calls', 'Only Missed Calls'),
    ('voicemails', 'Only Calls with Voicemails'),
)

ALERT_TYPES = (
    ('email', 'Email'),
)

SHOPIFY_USAGE_STATUSES = (
    ('not_paid', 'paid'),
)


class TwilioAutomation(models.Model):
    DEFAULT_TITLE = "Untitled CallFlow"
    user = models.ForeignKey(User, related_name='twilio_automations', null=True, blank=True, on_delete=models.CASCADE)

    title = models.CharField(max_length=255, default='')
    first_step = models.IntegerField(default=0)
    last_step = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, null=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    @cached_property
    def json_data(self):
        serialized_data = [s.serializable_object() for s in self.steps.filter(parent__isnull=True)]
        return json.dumps(serialized_data)

    def __str__(self):
        return self.title or self.DEFAULT_TITLE


class TwilioStep(models.Model):
    automation = models.ForeignKey(TwilioAutomation, related_name='steps', on_delete=models.CASCADE)
    parent = models.ForeignKey('self', null=True, related_name='children', on_delete=models.CASCADE)
    block_type = models.CharField(max_length=100)
    step = models.IntegerField(default=0, null=True)
    next_step = models.IntegerField(default=0, null=True)
    config = models.TextField(default='{}')

    class Meta:
        ordering = ('pk',)

    def get_config(self):
        try:
            return json.loads(self.config)
        except:
            return {}

    def serializable_object(self):
        step = model_to_dict(self)
        step['children'] = []
        step['config'] = self.get_config()

        if not self.parent:
            step['parent'] = 0
        else:
            step['parent'] = self.parent.step

        del step['automation']
        del step['id']

        for children_step in self.children.select_related('parent').all():
            step['children'].append(children_step.serializable_object())

        return step

    @property
    def url(self):
        raw_url = {
            'flow-block-greeting': reverse('phone_automation_call_flow_speak'),
            'flow-block-menu': reverse('phone_automation_call_flow_menu'),
            'flow-block-record': reverse('phone_automation_call_flow_record'),
            'flow-block-dial': reverse('phone_automation_call_flow_dial'),
        }.get(self.block_type, reverse('phone_automation_call_flow_empty'))

        raw_url += '?step={}'.format(self.step)
        return raw_url

    @cached_property
    def redirect(self):
        if self.next_step is None:
            # Search next step backwards
            parent = self.parent
            current_step = self.step
            while parent is not None:
                if parent.next_step == current_step:
                    parent = parent.parent
                    current_step = parent.step
                else:
                    return parent.redirect

            return reverse('phone_automation_call_flow_hangup')

        next_step = self.automation.steps.get(step=self.next_step)
        return next_step.url


class TwilioCompany(models.Model):
    user = models.ForeignKey(User, related_name='twilio_companies', on_delete=models.CASCADE)
    title = models.CharField(max_length=255, default='')
    timezone = models.CharField(max_length=255, default='')
    config = models.TextField(default='{}')

    def get_config(self):
        try:
            return json.loads(self.config)
        except:
            return {}

    def get_profile_users(self):
        profile_user = {"email": self.user.email, "name": self.user.get_full_name()}
        return [profile_user]

    def get_config_users(self):
        return self.get_config().get('users', [])

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return self.title


class TwilioPhoneNumber(models.Model):
    user = models.ForeignKey(User, related_name='twilio_phone_numbers', on_delete=models.CASCADE)
    automation = models.ForeignKey(TwilioAutomation, related_name='phones', null=True, blank=True, on_delete=models.CASCADE)
    company = models.ForeignKey(TwilioCompany, related_name='phones', null=True, blank=True, on_delete=models.CASCADE)
    title = models.CharField(max_length=255, default='')

    incoming_number = models.CharField(max_length=50, default='', blank=True)
    forwarding_number = models.CharField(max_length=50, default='', blank=True)
    status = models.CharField(max_length=50, default='', choices=PHONE_NUMBER_STATUSES)
    type = models.CharField(max_length=50, default='tollfree', choices=PHONE_NUMBER_TYPES)
    country_code = models.CharField(max_length=10, default='', blank=True)
    twilio_sid = models.CharField(max_length=50, default='', blank=True)
    twilio_metadata = JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    sms_enabled = models.BooleanField(default=False)
    custom_subscription = models.ForeignKey(CustomStripeSubscription, related_name='twilio_phone_numbers', null=True,
                                            blank=True, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    class Meta:
        ordering = ('pk',)

    @property
    def twilio_metadata_json(self):
        if isinstance(self.twilio_metadata, str):
            return json.loads(self.twilio_metadata)
        else:
            return self.twilio_metadata

    def __str__(self):
        return f'{self.title} ({self.incoming_number})'

    def refresh_phone_properties(self):
        if not settings.DEBUG and self.twilio_sid:
            client = get_twilio_client()
            number = client.incoming_phone_numbers(self.twilio_sid).fetch()
            self.twilio_metadata = number._properties

    def last_two_month_usage(self):
        date_start = arrow.get(timezone.now()).replace(hour=0, minute=0, second=0, day=1, months=-1).datetime
        queryset = self.user.twilio_logs.filter(
            log_type='status-callback',
            created_at__gte=date_start
        ).extra({
            'date_key': 'EXTRACT(MONTH FROM created_at)'
        }).values('date_key').annotate(
            seconds=models.Sum('call_duration')
        ).order_by('date_key')

        monthly_totals = []
        for row in queryset:
            month = calendar.month_name[int(row.get('date_key'))]
            seconds = row.get('seconds')
            monthly_totals.append(f'{month}: {seconds} seconds')

        return ' - '.join(monthly_totals)

    def delete(self, *args, **kwargs):
        try:
            client = get_twilio_client()
            client.incoming_phone_numbers(self.twilio_sid).delete()
        except:
            pass
        super(TwilioPhoneNumber, self).delete(*args, **kwargs)

    def safe_delete(self, *args, **kwargs):
        try:
            client = get_twilio_client()
            client.incoming_phone_numbers(self.twilio_sid).delete()
        except:
            pass
        self.status = "released"
        self.save()

    @property
    def removable(self):
        removal_avail_date = self.created_at + timedelta(days=30)
        if not self.user.can('phone_automation_unlimited_phone_numbers.use') and timezone.now() < removal_avail_date:
            return False
        else:
            return True

    @property
    def date_remove_allowed(self):
        return self.created_at + timedelta(days=30)


class TwilioUpload(models.Model):
    class Meta:
        ordering = ['-created_at']
    user = models.ForeignKey(User, related_name='twilio_uploads', on_delete=models.CASCADE)
    # phone = models.ForeignKey(TwilioPhoneNumber, on_delete=models.CASCADE)
    automation = models.ForeignKey(TwilioAutomation, related_name='automation', null=True, on_delete=models.CASCADE)
    url = models.CharField(max_length=512, blank=True, default='', verbose_name="Upload file URL")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return self.url.replace('%2F', '/').split('/')[-1]


class TwilioLog(models.Model):
    user = models.ForeignKey(User, related_name='twilio_logs', on_delete=models.CASCADE)
    twilio_phone_number = models.ForeignKey(TwilioPhoneNumber, related_name='twilio_logs', null=True, on_delete=models.CASCADE)
    direction = models.CharField(max_length=50, default='', blank=True)
    from_number = models.CharField(max_length=50, default='', blank=True)
    call_duration = models.IntegerField(default=0, null=True)
    call_sid = models.CharField(max_length=50, default='', blank=True)
    call_status = models.CharField(max_length=50, default='', blank=True)
    log_type = models.CharField(max_length=50, default='', blank=True)
    phone_type = models.CharField(max_length=50, default='tollfree', choices=PHONE_NUMBER_TYPES)
    digits = models.CharField(max_length=50, default='', blank=True)
    twilio_metadata = JSONField(default=dict)
    notes = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')
    deleted_at = models.DateTimeField(null=True, blank=True)

    @property
    def twilio_metadata_json(self):
        if isinstance(self.twilio_metadata, str):
            return json.loads(self.twilio_metadata)
        else:
            return self.twilio_metadata

    class Meta:
        ordering = ('-created_at',)


class TwilioRecording(models.Model):
    twilio_log = models.ForeignKey(TwilioLog, related_name='twilio_recordings', on_delete=models.CASCADE)
    recording_sid = models.CharField(max_length=50, default='', blank=True)
    recording_url = models.CharField(max_length=300, default='', blank=True)
    twilio_metadata = JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')


# Signals
@receiver(post_save, sender=TwilioUpload)
def convert_callflow_audio_file(sender, instance, created, **kwargs):
    file_path = urlsplit(instance.url).path
    file_path = file_path.lstrip('/')  # Removes initial slash(/) char
    output_path = '{}.converted.mp3'.format(file_path)

    key = aws_s3_get_key(output_path, bucket_name=settings.S3_UPLOADS_BUCKET)
    if key:
        key.delete()

    client = boto.elastictranscoder.connect_to_region('us-east-1')
    client.create_job(
        pipeline_id=settings.AWS_AUDIO_TRANSCODE_PIPELINE_ID,
        input_name={
            'Key': file_path  # file path in S3
        },
        outputs=[{
            'Key': output_path,
            'PresetId': '1351620000001-300040',  # MP3 128K
        }]
    )


class CallflexCreditsPlan(models.Model):
    allowed_credits = models.IntegerField(default=0)
    amount = models.IntegerField(default=0, verbose_name='In USD')

    def __unicode__(self):
        return f'{self.allowed_credtis} / {self.amount}'


class CallflexCredit(models.Model):
    class Meta:
        ordering = ('pk',)

    user = models.ForeignKey(User, related_name='callflex_credits', on_delete=models.CASCADE)

    purchased_credits = models.BigIntegerField(default=0)
    phone_type = models.CharField(max_length=50, default='tollfree', choices=PHONE_NUMBER_TYPES)
    stripe_invoice = models.CharField(max_length=50, default='', blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return f'{self.user.username} / {self.remaining_credits} Credits'


class TwilioAlert(models.Model):
    user = models.ForeignKey(User, related_name='twilio_alerts', on_delete=models.CASCADE)
    twilio_phone_number = models.ForeignKey(TwilioPhoneNumber, related_name='twilio_alerts', null=True, on_delete=models.CASCADE)
    company = models.ForeignKey(TwilioCompany, related_name='twilio_alerts', null=True, on_delete=models.CASCADE)
    config = models.TextField(default='{}')
    alert_event = models.CharField(max_length=50, default='', choices=ALERT_EVENTS)
    alert_type = models.CharField(max_length=50, default='', choices=ALERT_TYPES)

    def get_config(self):
        try:
            return json.loads(self.config)
        except:
            return {}

    def get_config_users(self):
        config_users = []
        try:
            config_users = self.get_config()['users']
        except:
            pass

        return config_users

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return self.title


class TwilioSummary(models.Model):
    user = models.ForeignKey(User, related_name='twilio_summaries', on_delete=models.CASCADE)
    company = models.ForeignKey(TwilioCompany, related_name='twilio_summaries', null=True, on_delete=models.CASCADE)
    config = models.TextField(default='{}')
    freq_daily = models.BooleanField(default=False)
    freq_weekly = models.BooleanField(default=False)
    freq_monthly = models.BooleanField(default=False)
    include_calllogs = models.BooleanField(default=False)

    def get_config(self):
        try:
            return json.loads(self.config)
        except:
            return {}

    def get_config_users(self):
        config_users = []
        try:
            config_users = self.get_config()['users']
        except:
            pass

        return config_users

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return self.title


class CallflexShopifyUsageCharge(models.Model):
    class Meta:
        ordering = ('pk',)

    user = models.ForeignKey(User, related_name='callflex_shopify_usage_charges', on_delete=models.CASCADE)
    type = models.CharField(max_length=50, default='', blank=True)
    status = models.CharField(max_length=50, default='not_paid', choices=SHOPIFY_USAGE_STATUSES)
    amount = models.DecimalField(decimal_places=2, max_digits=9, verbose_name='Amount(in USD)', default=0)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')
