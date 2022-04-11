import os

from django import forms
from django.core.exceptions import ValidationError

from addons_core.forms import URLFileInputWidget
from insider_reports.utils import upload_report_to_aws


def validate_file_extension(value):
    ext = os.path.splitext(value.name)[1]  # [0] returns path+filename
    valid_extensions = ['.pdf', ]
    if not ext.lower() in valid_extensions:
        raise ValidationError('Unsupported file extension.')


class InsiderReportForm(forms.ModelForm):
    report_url = forms.FileField(widget=URLFileInputWidget(), validators=[validate_file_extension])
    request = None

    def clean_report_url(self):
        report = self.cleaned_data['report_url']
        if report and not isinstance(report, str):
            return upload_report_to_aws(report, 'insider-reports')

        return report
