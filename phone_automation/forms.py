import json

from django import forms

from phone_automation.models import TwilioAlert, TwilioAutomation, TwilioCompany, TwilioPhoneNumber, TwilioStep, TwilioSummary


class TwilioAutomationForm(forms.ModelForm):
    children = forms.CharField(widget=forms.Textarea, required=False)

    def save(self, commit=True):
        automation = super(TwilioAutomationForm, self).save(commit=commit)
        flow = self.cleaned_data.get('children', None) or '[]'

        def save_all_steps(node, parent=None):
            """ Save each node in correct order
            """
            if node.get('step', 0) != 0:
                parent = TwilioStep.objects.create(
                    automation=automation,
                    parent=parent,
                    block_type=node.get('block_type'),
                    step=node.get('step'),
                    next_step=node.get('next_step'),
                    config=json.dumps(node.get('config')),
                )

            if len(node.get('children')):
                for node in node.get('children'):
                    save_all_steps(node, parent)

        if flow:
            automation.steps.all().delete()
            save_all_steps({'children': json.loads(flow)})

        return automation

    class Meta:
        model = TwilioAutomation
        exclude = ('user',)


class TwilioPhoneNumberForm(forms.ModelForm):
    automation = forms.ModelChoiceField(queryset=None, empty_label="Forward All Calls to ...", required=False)
    company = forms.ModelChoiceField(queryset=None, empty_label="Not Selected", required=False)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super(TwilioPhoneNumberForm, self).__init__(*args, **kwargs)
        self.fields["automation"].queryset = user.twilio_automations
        self.fields["company"].queryset = user.twilio_companies

    class Meta:
        model = TwilioPhoneNumber
        fields = ['automation', 'title', 'sms_enabled', 'company', 'forwarding_number']
        exclude = ('user',)


class TwilioProvisionForm(forms.Form):
    title = forms.CharField(max_length=100, required=False)
    automation = forms.ModelChoiceField(queryset=None, empty_label="Forward All Calls to ...", required=False)
    company = forms.ModelChoiceField(queryset=None, empty_label="Not Selected", required=False)
    sms_enabled = forms.BooleanField(required=False)
    forwarding_number = forms.CharField(max_length=50, required=False)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super(TwilioProvisionForm, self).__init__(*args, **kwargs)
        self.fields["automation"].queryset = user.twilio_automations
        self.fields["company"].queryset = user.twilio_companies


class TwilioCompanyForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(TwilioCompanyForm, self).__init__(*args, **kwargs)

    class Meta:
        model = TwilioCompany
        fields = ['title', ]
        exclude = ('user', 'timezone', 'config')


class TwilioAlertForm(forms.ModelForm):
    twilio_phone_number = forms.ModelChoiceField(queryset=None, empty_label="All Phones", required=False)

    def __init__(self, *args, **kwargs):
        super(TwilioAlertForm, self).__init__(*args, **kwargs)
        self.fields["twilio_phone_number"].queryset = self.instance.company.phones

    class Meta:
        model = TwilioAlert
        fields = ['twilio_phone_number', 'alert_event', 'alert_type']
        exclude = ('user', 'config', 'company')


class TwilioSummaryForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(TwilioSummaryForm, self).__init__(*args, **kwargs)

    class Meta:
        model = TwilioSummary
        fields = ['freq_daily', 'freq_weekly', 'freq_monthly', 'include_calllogs']
        exclude = ('user', 'config', 'company')
