# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin

from .forms import TwilioAutomationForm
from .models import (
    TwilioAutomation,
    TwilioPhoneNumber,
    TwilioStep,
    TwilioUpload,
    TwilioLog,
    TwilioRecording
)


@admin.register(TwilioAutomation)
class TwilioAutomationAdmin(admin.ModelAdmin):
    form = TwilioAutomationForm

    list_display = ('numbers', 'first_step', 'last_step')
    search_fields = ('phone__incoming_number',)
    raw_id_fields = ('user',)

    def get_form(self, request, instance=None, **kwargs):
        """ Defines as initial value the automation flow as json
        """
        form = super(TwilioAutomationAdmin, self).get_form(request, instance, **kwargs)
        if instance:
            form.base_fields['children'].initial = instance.json_data

        return form

    def numbers(self, obj):
        return u','.join([p.incoming_number for p in obj.phone.all()])


@admin.register(TwilioPhoneNumber)
class TwilioPhoneNumberAdmin(admin.ModelAdmin):
    list_display = ('incoming_number', 'status', 'twilio_sid', 'created_at')
    search_fields = ('user__email', 'incoming_number')
    raw_id_fields = ('user', 'automation')


@admin.register(TwilioStep)
class TwilioStepAdmin(admin.ModelAdmin):
    list_display = ('numbers', 'step', 'block_type', 'config')
    search_fields = ('automation__phone__incoming_number', 'step', 'block_type')
    raw_id_fields = ('automation',)

    def numbers(self, obj):
        return u','.join([p.incoming_number for p in obj.automation.phone.all()])


@admin.register(TwilioUpload)
class TwilioUploadAdmin(admin.ModelAdmin):
    list_display = ('url', 'created_at')
    search_fields = ('automation__phone__incoming_number', 'user__email')
    raw_id_fields = ('user', 'phone')


@admin.register(TwilioLog)
class TwilioLogAdmin(admin.ModelAdmin):
    list_display = ('direction', 'from_number', 'call_duration', 'call_sid', 'call_status', 'log_type')
    search_fields = ('user__email', 'from_number')
    raw_id_fields = ('user',)


@admin.register(TwilioRecording)
class TwilioRecordingAdmin(admin.ModelAdmin):
    list_display = ('recording_sid', 'recording_url')
    search_fields = ('twilio_log__user__email', 'twilio_log__from_number')
    raw_id_fields = ('twilio_log',)
