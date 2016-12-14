import re
from json import loads

from django import forms
from django.contrib.auth.models import User
from django.core.validators import validate_email, ValidationError


class OrderExportForm(forms.Form):
    receiver = forms.CharField(required=False)  # e-mails

    vendor = forms.CharField(required=False)

    status = forms.CharField(required=False)
    fulfillment_status = forms.CharField(required=False)
    financial_status = forms.CharField(required=False)

    daterange = forms.CharField(required=False)
    schedule = forms.TimeField(required=False, input_formats=['%H:%M'])
    previous_day = forms.BooleanField(required=False, initial=True)

    fields = forms.CharField(required=False)
    line_fields = forms.CharField(required=False)
    shipping_address = forms.CharField(required=False)

    vendor_user = forms.IntegerField(required=False)
    vendor_username = forms.CharField(required=False)
    vendor_email = forms.EmailField(required=False)

    def validate_email_list(self, value):
        SEPARATOR_RE = re.compile(r'[,;]+')
        emails = SEPARATOR_RE.split(value)
        for email in emails:
            validate_email(email.strip(' '))

    def clean(self):
        form_data = self.cleaned_data

        fields = loads(form_data.get('fields', '[]'))
        line_fields = loads(form_data.get('line_fields', '[]'))
        shipping_address = loads(form_data.get('shipping_address', '[]'))

        if len(fields) == 0 and len(line_fields) == 0 and len(shipping_address) == 0:
            self.add_error('fields', 'Please, add at least one field for the header.')
            self.add_error('line_fields', 'Please, add at least one field for the header.')
            self.add_error('shipping_address', 'Please, add at least one field for the header.')

        previous_day = form_data.get('previous_day')
        if previous_day:
            # daily
            receiver = form_data.get('receiver')
            if not receiver:
                self.add_error('receiver', 'This field is required for daily run exports.')
            else:
                try:
                    self.validate_email_list(receiver)
                except ValidationError as e:
                    self.add_error('receiver', e.message)

            schedule = form_data.get('schedule')
            if not schedule:
                self.add_error('schedule', 'This field is required for daily run exports.')

            vendor_user = form_data.get('vendor_user')
            vendor_username = form_data.get('vendor_username')
            vendor_email = form_data.get('vendor_email')
            if not vendor_user and (not vendor_username or not vendor_email):
                self.add_error('vendor_username', 'A user needs to be added to access the generated orders page.')
            elif not vendor_user:
                if not vendor_username:
                    self.add_error('vendor_username', 'A user needs to be added to access the generated orders page.')
                if not vendor_email:
                    self.add_error('vendor_email', 'You need to set an e-mail for the user.')
        else:
            # single
            daterange = form_data.get('daterange')
            if not daterange:
                self.add_error('daterange', 'This field is required for single run exports.')

        return form_data

    def clean_vendor_username(self):
        vendor_username = self.cleaned_data.get('vendor_username')
        if vendor_username:
            found_user = User.objects.filter(username=vendor_username).count()
            if found_user > 0:
                self.add_error('vendor_username', 'Username already exists.')

        return vendor_username
