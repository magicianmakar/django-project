from json import loads

from django import forms


class OrderExportForm(forms.Form):
    schedule = forms.TimeField(input_formats=['%H:%M'])
    receiver = forms.EmailField()

    vendor = forms.CharField(required=False)

    status = forms.CharField(required=False)
    fulfillment_status = forms.CharField(required=False)
    financial_status = forms.CharField(required=False)

    fields = forms.CharField(required=False)
    line_fields = forms.CharField(required=False)
    shipping_address = forms.CharField(required=False)

    def clean(self):
        form_data = self.cleaned_data

        fields = loads(form_data.get('fields', '[]'))
        line_fields = loads(form_data.get('line_fields', '[]'))
        shipping_address = loads(form_data.get('shipping_address', '[]'))

        if len(fields) == 0 and len(line_fields) == 0 and len(shipping_address) == 0:
            self.add_error('fields', 'Please, add at least one field for the header.')
            self.add_error('line_fields', 'Please, add at least one field for the header.')
            self.add_error('shipping_address', 'Please, add at least one field for the header.')

        return form_data

