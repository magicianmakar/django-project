from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

from .models import Payout, PLSOrder, PLSupplement, UserSupplement, UserSupplementLabel


class UserSupplementForm(forms.ModelForm):
    class Meta:
        model = UserSupplement
        fields = ['title',
                  'description',
                  'category',
                  'tags',
                  'price',
                  'compare_at_price',
                  ]

        widgets = {
            'tags': forms.TextInput(),
        }

    cost_price = forms.DecimalField()
    shipstation_sku = forms.CharField()
    shipping_countries = forms.CharField(required=False)
    action = forms.CharField(widget=forms.HiddenInput)
    upload = forms.FileField(required=False)
    image_data_url = forms.CharField(widget=forms.HiddenInput, required=False)

    def clean_upload(self):
        upload = self.cleaned_data['upload']
        if self.cleaned_data['action'] == 'approve':
            if not upload:
                raise ValidationError("Label is required.")

            extension_validator = FileExtensionValidator(
                allowed_extensions=['pdf']
            )
            extension_validator(upload)
        elif upload:
            extension_validator = FileExtensionValidator(
                allowed_extensions=['png', 'jpg', 'jpeg']
            )
            extension_validator(upload)


class CommentForm(forms.Form):
    comment = forms.CharField(widget=forms.Textarea)
    action = forms.CharField(widget=forms.HiddenInput)
    upload = forms.FileField(required=False)

    def clean_upload(self):
        if self.cleaned_data['action'] == 'comment':
            upload = self.cleaned_data['upload']
            if not upload:
                return

            extension_validator = FileExtensionValidator(
                allowed_extensions=['pdf']
            )
            extension_validator(upload)


class PLSupplementForm(forms.ModelForm):
    class Meta:
        model = PLSupplement
        fields = ['title',
                  'description',
                  'category',
                  'tags',
                  'shipstation_sku',
                  'cost_price',
                  'shipping_countries',
                  'wholesale_price',
                  ]

        widgets = {
            'tags': forms.TextInput(),
        }

    template = forms.FileField()
    thumbnail = forms.ImageField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['shipping_countries'].required = False

    def clean_template(self):
        template = self.cleaned_data['template']
        if not template:
            return

        extension_validator = FileExtensionValidator(
            allowed_extensions=['pdf']
        )
        extension_validator(template)


class OrderFilterForm(forms.Form):
    STATUSES = [('', '-')] + PLSOrder.STATUSES

    order_number = forms.CharField(required=False)
    status = forms.ChoiceField(required=False, choices=STATUSES)
    email = forms.CharField(required=False)
    refnum = forms.CharField(required=False, label='Payout ID')
    amount = forms.DecimalField(required=False)
    date = forms.DateField(required=False)


class MyOrderFilterForm(forms.Form):
    order_number = forms.CharField(required=False)
    stripe_id = forms.CharField(required=False)
    date = forms.DateField(required=False)


class PayoutFilterForm(OrderFilterForm):
    STATUSES = [('', '-')] + Payout.STATUSES

    status = forms.ChoiceField(required=False, choices=STATUSES)


class LineFilterForm(OrderFilterForm):
    LINE_STATUSES = [
        ('', '-'),
        ('not-printed', 'Not Printed'),
        ('printed', 'Printed'),
    ]

    line_status = forms.ChoiceField(required=False, choices=LINE_STATUSES)
    product_sku = forms.CharField(required=False)
    label_sku = forms.CharField(required=False)


class LabelFilterForm(forms.Form):
    STATUSES = [('', '-')] + UserSupplementLabel.LABEL_STATUSES

    status = forms.ChoiceField(required=False, choices=STATUSES)
    sku = forms.CharField(required=False)
    date = forms.DateField(required=False)


class BillingForm(forms.Form):
    name = forms.CharField()
    cc_number = forms.CharField(max_length=16)
    cc_expiry = forms.CharField()
    cc_cvv = forms.CharField(max_length=3)
    address_line1 = forms.CharField()
    address_line2 = forms.CharField(required=False)
    address_city = forms.CharField()
    address_state = forms.CharField()
    address_zip = forms.CharField(max_length=5)
    address_country = forms.CharField(max_length=5)


class PayoutForm(forms.ModelForm):
    class Meta:
        model = Payout
        fields = [
            'reference_number',
        ]


class UploadJSONForm(forms.Form):
    upload = forms.FileField()

    def clean_upload(self):
        upload = self.cleaned_data['upload']
        if not upload:
            return

        extension_validator = FileExtensionValidator(
            allowed_extensions=['json']
        )
        extension_validator(upload)
