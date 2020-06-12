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
import csv
from django.http import HttpResponse


class ExportCsvMixin:
    def export_as_csv(self, request, queryset):

        meta = self.model._meta
        field_names = [field.name for field in meta.fields]

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename={}.csv'.format(meta)
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            writer.writerow([getattr(obj, field) for field in field_names])

        return response

    export_as_csv.short_description = "Export Selected"


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
    list_display = ('incoming_number', 'status', 'twilio_sid', 'created_at', 'user', 'plan', 'last_two_month_usage')
    search_fields = ('user__email', 'incoming_number', 'user__profile__plan__title')
    raw_id_fields = ('automation', 'user')
    readonly_fields = ('last_two_month_usage', )
    list_filter = ('status', 'user__profile__plan')
    actions = (ExportCsvMixin.export_as_csv,)
    list_max_show_all = 100

    def plan(self, obj):
        return obj.user.profile.plan

    def save_model(self, request, instance, *args, **kwargs):
        instance.refresh_phone_properties()

        super(TwilioPhoneNumberAdmin, self).save_model(request, instance, *args, **kwargs)


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
    list_display = ('created_at', 'direction', 'from_number', 'call_duration', 'call_sid', 'call_status', 'log_type', 'to_number')
    search_fields = ('user__email', 'from_number', 'to_number', 'call_sid')
    raw_id_fields = ('user',)
    list_filter = ('direction', 'call_status', 'created_at')
    actions = (ExportCsvMixin.export_as_csv,)
    list_max_show_all = 100

    def to_number(self, obj):
        return obj.twilio_metadata['To']


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
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'
