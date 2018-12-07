# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json

from django.contrib.auth.models import User
from django.db import models
from django.contrib.postgres.fields import JSONField
from django.forms.models import model_to_dict
from django.utils.functional import cached_property
from django.urls import reverse

PHONE_NUMBER_STATUSES = (
    ('active', 'Incoming calls allowed'),
    ('inactive', 'Forwardning all incoming calls'),
)


class TwilioAutomation(models.Model):
    user = models.ForeignKey(User, related_name='twilio_automations', null=True, on_delete=models.CASCADE)

    title = models.CharField(max_length=255, default='')
    first_step = models.IntegerField(default=0)
    last_step = models.IntegerField(default=0)

    @cached_property
    def json_data(self):
        serialized_data = [s.serializable_object() for s in self.steps.filter(parent__isnull=True)]
        return json.dumps(serialized_data)


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

        raw_url += u'?step={}'.format(self.step)
        return raw_url

    @cached_property
    def redirect(self):
        if self.next_step is None:
            return reverse('phone_automation_call_flow_hangup')

        next_step = self.automation.steps.get(step=self.next_step)
        return next_step.url


class TwilioPhoneNumber (models.Model):
    user = models.OneToOneField(User, related_name='twilio_phone_number', on_delete=models.CASCADE)
    automation = models.ForeignKey(TwilioAutomation, related_name='phone', null=True)

    incoming_number = models.CharField(max_length=50, default='', blank=True)
    forwarding_number = models.CharField(max_length=50, default='', blank=True)
    status = models.CharField(max_length=50, default='', choices=PHONE_NUMBER_STATUSES)
    country_code = models.CharField(max_length=10, default='', blank=True)
    twilio_sid = models.CharField(max_length=50, default='', blank=True)
    twilio_metadata = JSONField(default={})

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return self.incoming_number


class TwilioUpload(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    phone = models.ForeignKey(TwilioPhoneNumber, on_delete=models.CASCADE)
    url = models.CharField(max_length=512, blank=True, default='', verbose_name="Upload file URL")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return self.url.replace('%2F', '/').split('/')[-1]


class TwilioLog (models.Model):
    user = models.ForeignKey(User, related_name='twilio_logs', on_delete=models.CASCADE)
    direction = models.CharField(max_length=50, default='', blank=True)
    from_number = models.CharField(max_length=50, default='', blank=True)
    call_duration = models.IntegerField(default=0, null=True)
    call_sid = models.CharField(max_length=50, default='', blank=True)
    call_status = models.CharField(max_length=50, default='', blank=True)
    log_type = models.CharField(max_length=50, default='', blank=True)
    digits = models.CharField(max_length=50, default='', blank=True)
    twilio_metadata = JSONField(default={})

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    class Meta:
        ordering = ('-created_at',)


class TwilioRecording(models.Model):
    twilio_log = models.ForeignKey(TwilioLog, related_name='twilio_recordings', on_delete=models.CASCADE)
    recording_sid = models.CharField(max_length=50, default='', blank=True)
    recording_url = models.CharField(max_length=300, default='', blank=True)
    twilio_metadata = JSONField(default={})

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')
