from django.contrib import admin

from .forms import TwilioAutomationForm
from .models import (
    TwilioAutomation,
    TwilioPhoneNumber,
    TwilioStep,
    TwilioUpload,
    TwilioLog,
    TwilioRecording,
    CallflexCreditsPlan,
    TwilioCompany,
    TwilioAlert,
    TwilioSummary,
    CallflexShopifyUsageCharge,
)


@admin.register(TwilioAutomation)
class TwilioAutomationAdmin(admin.ModelAdmin):
    form = TwilioAutomationForm

    list_display = ('id', 'title', 'numbers', 'first_step', 'last_step')
    search_fields = ('phones__incoming_number',)
    raw_id_fields = ('user',)

    def get_form(self, request, instance=None, **kwargs):
        """ Defines as initial value the automation flow as json
        """
        form = super(TwilioAutomationAdmin, self).get_form(request, instance, **kwargs)
        if instance:
            form.base_fields['children'].initial = instance.json_data

        return form

    def numbers(self, obj):
        return ','.join([p.incoming_number for p in obj.phones.all()])


@admin.register(TwilioPhoneNumber)
class TwilioPhoneNumberAdmin(admin.ModelAdmin):
    list_display = ('incoming_number', 'status', 'twilio_sid', 'created_at')
    search_fields = ('user__email', 'incoming_number')
    raw_id_fields = ('user', 'automation')
    readonly_fields = ('last_two_month_usage', )


@admin.register(TwilioStep)
class TwilioStepAdmin(admin.ModelAdmin):
    list_display = ('numbers', 'step', 'block_type', 'config')
    search_fields = ('automation__phone__incoming_number', 'step', 'block_type')
    raw_id_fields = ('automation',)

    def numbers(self, obj):
        return ','.join([p.incoming_number for p in obj.automation.phone.all()])


@admin.register(TwilioUpload)
class TwilioUploadAdmin(admin.ModelAdmin):
    list_display = ('url', 'created_at')
    search_fields = ('automation__title', 'user__email')
    raw_id_fields = ('user', 'automation')


@admin.register(TwilioLog)
class TwilioLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'direction', 'from_number', 'call_duration', 'call_sid', 'call_status', 'log_type')
    search_fields = ('user__email', 'from_number')
    raw_id_fields = ('user',)


@admin.register(TwilioRecording)
class TwilioRecordingAdmin(admin.ModelAdmin):
    list_display = ('recording_sid', 'recording_url')
    search_fields = ('twilio_log__user__email', 'twilio_log__from_number')
    raw_id_fields = ('twilio_log',)


@admin.register(CallflexCreditsPlan)
class CallflexCreditsPlanAdmin(admin.ModelAdmin):
    list_display = ('allowed_credits', 'amount')
    search_fields = ('allowed_credits', 'amount')
    raw_id_fields = ()


@admin.register(TwilioCompany)
class TwilioCompanyAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'title',
        'timezone',
        'config',
        'created_at',
        'updated_at',
    )
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'


@admin.register(TwilioAlert)
class TwilioAlertAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'twilio_phone_number',
        'company',
        'config',
        'alert_event',
        'alert_type',
        'created_at',
        'updated_at',
    )
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('user', 'twilio_phone_number', 'company')
    date_hierarchy = 'created_at'


@admin.register(TwilioSummary)
class TwilioSummaryAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'company',
        'config',
        'freq_daily',
        'freq_weekly',
        'freq_monthly',
        'include_calllogs',
        'created_at',
        'updated_at',
    )
    list_filter = (
        'freq_daily',
        'freq_weekly',
        'freq_monthly',
        'include_calllogs',
        'created_at',
        'updated_at',
    )
    raw_id_fields = ('user', 'company')
    date_hierarchy = 'created_at'


@admin.register(CallflexShopifyUsageCharge)
class CallflexShopifyUsageChargeAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'type',
        'status',
        'created_at',
        'updated_at',
    )
    list_filter = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
