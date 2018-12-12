import json

from django import forms

from phone_automation.models import TwilioAutomation, TwilioStep


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
        exclude = ('title',)
