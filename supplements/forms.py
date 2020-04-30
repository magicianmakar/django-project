from django import forms
from django.core.validators import FileExtensionValidator

from .models import LabelSize, Payout, PLSOrder, PLSupplement, UserSupplement, UserSupplementLabel


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
    mockup_type = forms.CharField(required=False)
    label_size = forms.CharField(required=False)
    action = forms.CharField(widget=forms.HiddenInput)
    image_data_url = forms.CharField(widget=forms.HiddenInput, required=False)
    upload_url = forms.CharField(widget=forms.HiddenInput, required=False)
    mockup_slug = forms.CharField(widget=forms.HiddenInput, required=False)
    weight = forms.DecimalField()


class CommentForm(forms.Form):
    comment = forms.CharField(widget=forms.Textarea)
    action = forms.CharField(widget=forms.HiddenInput)
    upload_url = forms.CharField(widget=forms.HiddenInput, required=False)
    image_data_url = forms.CharField(widget=forms.HiddenInput, required=False)
    mockup_slug = forms.CharField(widget=forms.HiddenInput, required=False)


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
                  'product_information',
                  'label_size',
                  'weight',
                  'mockup_type',
                  'is_active',
                  ]

        widgets = {
            'tags': forms.TextInput(),
            'shipping_countries': forms.SelectMultiple(attrs={'data-placeholder': 'Select shipping countries'})
        }

    template = forms.FileField()
    thumbnail = forms.ImageField()
    approvedlabel = forms.FileField(required=False)
    authenticity_certificate = forms.FileField(required=False)

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

    def clean_authenticity_certificate(self):
        cert = self.cleaned_data['authenticity_certificate']
        if not cert:
            return

        extension_validator = FileExtensionValidator(
            allowed_extensions=['pdf']
        )
        extension_validator(cert)


class PLSupplementEditForm(PLSupplementForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['template'].required = False
        self.fields['thumbnail'].required = False


class OrderFilterForm(forms.Form):
    STATUSES = [('', '---------')] + PLSOrder.STATUSES

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
        ('', '---------'),
        ('not-printed', 'Not Printed'),
        ('printed', 'Printed'),
    ]

    SHIPSTATION_STATUSES = [
        ('', '---------'),
        ('fulfilled', 'Fulfilled'),
        ('unfulfilled', 'Unfulfilled'),
    ]

    line_status = forms.ChoiceField(required=False, choices=LINE_STATUSES)
    label_size = forms.ModelChoiceField(required=False, queryset=LabelSize.objects.all())
    product_sku = forms.CharField(required=False)
    label_sku = forms.CharField(required=False)
    batch_number = forms.CharField(required=False)
    shipstation_status = forms.ChoiceField(required=False, choices=SHIPSTATION_STATUSES)


class LabelFilterForm(forms.Form):
    STATUSES = [('', '---------')] + [i for i in UserSupplementLabel.LABEL_STATUSES
                                      if i[0] != 'draft']

    status = forms.ChoiceField(required=False, choices=STATUSES)
    sku = forms.CharField(required=False)
    date = forms.DateField(required=False)


class AllLabelFilterForm(forms.Form):
    label_user_id = forms.IntegerField(required=False)
    product_sku = forms.CharField(required=False)
    title = forms.CharField(required=False)


class BillingForm(forms.Form):
    name = forms.CharField()
    cc_number = forms.CharField(max_length=16)
    cc_expiry = forms.CharField()
    cc_cvv = forms.CharField(max_length=3)
    address_line1 = forms.CharField()
    address_line2 = forms.CharField(required=False)
    address_city = forms.CharField()
    address_state = forms.CharField()
    address_zip = forms.CharField(max_length=10)
    address_country = forms.CharField(max_length=5)

    def __init__(self, data=None, *args, **kwargs):
        if data is not None:
            data = data.copy()  # make it mutable
            data['cc_number'] = ''.join(data['cc_number'].strip().split())

        super(BillingForm, self).__init__(data, *args, **kwargs)


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
