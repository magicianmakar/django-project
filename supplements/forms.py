from django import forms
from django.core.validators import FileExtensionValidator

from .models import LabelSize, Payout, PLSOrder, PLSupplement, UserSupplement, UserSupplementLabel, RefundPayments


class UserSupplementForm(forms.ModelForm):
    class Meta:
        model = UserSupplement
        fields = ['title',
                  'description',
                  'category',
                  'tags',
                  'price',
                  'compare_at_price',
                  'label_presets',
                  ]

        widgets = {
            'tags': forms.TextInput(),
        }

    cost_price = forms.DecimalField()
    shipstation_sku = forms.CharField()
    shipping_countries = forms.CharField(required=False)
    action = forms.CharField(widget=forms.HiddenInput)
    upload_url = forms.CharField(widget=forms.HiddenInput, required=False)
    mockup_slug = forms.CharField(widget=forms.HiddenInput, required=False)
    weight = forms.CharField()
    inventory = forms.IntegerField(required=False)
    msrp = forms.CharField(disabled=True, required=False)
    label_presets = forms.CharField(widget=forms.HiddenInput, required=False)


class UserSupplementFilterForm(forms.Form):
    STATUSES = [('', '---------')] + [i for i in UserSupplementLabel.LABEL_STATUSES]

    status = forms.ChoiceField(required=False, choices=STATUSES)
    sku = forms.CharField(required=False)
    title = forms.CharField(required=False)


class CommentForm(forms.Form):
    comment = forms.CharField(widget=forms.Textarea, required=False)
    action = forms.CharField(widget=forms.HiddenInput)
    upload_url = forms.CharField(widget=forms.HiddenInput, required=False)
    mockup_slug = forms.CharField(widget=forms.HiddenInput, required=False)
    is_private = forms.BooleanField(required=False)
    label_presets = forms.CharField(widget=forms.HiddenInput, required=False)
    # Placeholder field only used for validation
    mockup_urls = forms.CharField(widget=forms.HiddenInput, required=False)

    def clean(self):
        comment = self.cleaned_data.get('comment')
        upload_url = self.cleaned_data.get('upload_url')
        mockup_urls = self.cleaned_data.get('mockup_urls')
        if not comment and not upload_url and not mockup_urls:
            raise forms.ValidationError('A comment or a new label is required.')
        return self.cleaned_data


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
                  'msrp',
                  'mockup_type',
                  'is_active',
                  'inventory',
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


class PLSupplementFilterForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tags'].choices = [("", "Tagged with")] + list(PLSupplement.objects.values_list('tags', 'tags').distinct())
        self.fields['product_type'].choices = [("", "Product Type")] + list(PLSupplement.objects.values_list('category', 'category').distinct())

    title = forms.CharField(required=False)
    tags = forms.ChoiceField(required=False, choices=[])
    product_type = forms.ChoiceField(required=False, choices=[])


class OrderFilterForm(forms.Form):
    STATUSES = [('', '---------')] + PLSOrder.STATUSES

    order_number = forms.CharField(required=False)
    status = forms.ChoiceField(required=False, choices=STATUSES)
    email = forms.CharField(required=False)
    refnum = forms.CharField(required=False, label='Payout ID')
    amount = forms.DecimalField(required=False)
    date = forms.DateField(required=False)
    transactionid = forms.CharField(required=False)


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
    label_size = forms.ModelMultipleChoiceField(required=False, queryset=LabelSize.objects.all(),
                                                widget=forms.SelectMultiple(attrs={
                                                    'id': 'id_label_size_filter',
                                                    'data-placeholder': 'Select label sizes'
                                                }))
    product_sku = forms.MultipleChoiceField(required=False,
                                            widget=forms.SelectMultiple(
                                                attrs={'id': 'id_product_sku_filter', 'data-placeholder': 'Select product sku'}
                                            ))
    label_sku = forms.CharField(required=False)
    batch_number = forms.CharField(required=False)
    shipstation_status = forms.ChoiceField(required=False, choices=SHIPSTATION_STATUSES)
    cancelled = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super(LineFilterForm, self).__init__(*args, **kwargs)
        try:
            self.fields['product_sku'].choices = [(p.shipstation_sku, p.shipstation_sku) for p in PLSupplement.objects.all()]
        except:
            self.fields['product_sku'].choices = []


class LabelFilterForm(forms.Form):
    STATUSES = [i for i in UserSupplementLabel.LABEL_STATUSES
                if i[0] != 'draft']

    status = forms.MultipleChoiceField(required=False, choices=STATUSES,
                                       widget=forms.SelectMultiple(
                                           attrs={'id': 'id_label_sku_filter', 'data-placeholder': 'Select label status'}))
    sku = forms.CharField(required=False)
    date = forms.DateField(required=False)


class AllLabelFilterForm(forms.Form):
    SORT_STATUSES = [
        ('newest', 'Newest Labels First'),
        ('oldest', 'Oldest Labels First'),
    ]

    label_user_name = forms.CharField(required=False)
    product_sku = forms.MultipleChoiceField(required=False,
                                            widget=forms.SelectMultiple(attrs={
                                                'id': 'id_product_supplement_sku',
                                                'data-placeholder': 'Select product sku'}))
    title = forms.CharField(required=False)
    sort = forms.ChoiceField(required=False, choices=SORT_STATUSES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields['product_sku'].choices = [(p.shipstation_sku, p.shipstation_sku) for p in PLSupplement.objects.all()]
        except:
            self.fields['product_sku'].choices = []


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


class ReportsQueryForm(forms.Form):
    PERIODS = [
        ('', '---------'),
        ('week', 'Past 7 Days'),
        ('month', 'This Month'),
        ('year', 'This Year')
    ]
    INTERVALS = [
        ('day', 'Every Day'),
        ('week', 'Every Week'),
        ('month', 'Every Month')
    ]
    COMPARE_CHOICES = [
        ('', '---------'),
        ('2_week', 'Last 2 Weeks'),
        ('4_week', 'Last 4 Weeks'),
        ('2_month', 'Last 2 Months'),
        ('4_month', 'Last 4 Months'),
        ('2_year', 'Last 2 Years'),
    ]

    period = forms.ChoiceField(required=False, choices=PERIODS)
    start_date = forms.DateField(required=False)
    end_date = forms.DateField(required=False)
    interval = forms.ChoiceField(required=False, choices=INTERVALS)
    compare = forms.ChoiceField(required=False, choices=COMPARE_CHOICES)


class RefundPaymentsForm(forms.ModelForm):
    class Meta:
        model = RefundPayments
        fields = [
            'amount',
            'description',
            'fee',
            'item_shipped',
        ]

    def clean(self):
        super().clean()
        amount = self.cleaned_data.get('amount')
        fee = self.cleaned_data.get('fee')
        if amount <= fee:
            msg = 'Amount can not be less than or equal to Restocking Fee.'
            self.add_error('amount', msg)
