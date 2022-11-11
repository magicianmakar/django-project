import re

from django import forms
from django.core.validators import FileExtensionValidator

from leadgalaxy.models import UserProfile
from product_common.models import ProductSupplier
from .models import LabelSize, Payout, PLSOrder, PLSupplement, RefundPayments, UserSupplement, UserSupplementLabel, \
    ShipStationAccount


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
    label_size = forms.CharField(widget=forms.HiddenInput, required=False)


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
    label_size = forms.CharField(widget=forms.HiddenInput, required=False)
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
                  'is_discontinued',
                  'is_new',
                  'on_sale',
                  'inventory',
                  'supplier',
                  'shipstation_account',
                  'order_number_on_label',
                  'barcode_label',
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
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['shipping_countries'].required = False
        self.fields['shipstation_account'].required = True
        if self.user.can('pls_admin.use'):
            self.fields['supplier'].choices = [('', '---------')] + list(ProductSupplier.get_suppliers(shipping=False).values_list('id', 'title'))
        elif self.user.can('pls_supplier.use'):
            self.fields['supplier'].choices = [(self.user.profile.supplier.id, self.user.profile.supplier)]

        warehouse_account = UserProfile.objects.get(user=self.user.models_user.id).warehouse_account
        if warehouse_account:
            self.fields['shipstation_account'].queryset = ShipStationAccount.objects.filter(name=warehouse_account.name)

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
        self.fields['availability'].choices = [("In Stock", "In Stock"), ("All Products", "All Products"), ("New", "New"), ("Sale", "Sale")]

    title = forms.CharField(required=False)
    tags = forms.ChoiceField(required=False, choices=[])
    product_type = forms.ChoiceField(required=False, choices=[])
    availability = forms.ChoiceField(required=False, choices=[])


class OrderFilterForm(forms.Form):
    STATUSES = [('', '---------')] + PLSOrder.STATUSES

    order_number = forms.CharField(required=False)
    status = forms.ChoiceField(required=False, choices=STATUSES)
    email = forms.CharField(required=False)
    refnum = forms.CharField(required=False, label='Payout ID')
    amount = forms.DecimalField(required=False)
    transaction_id = forms.CharField(required=False)
    supplier = forms.ModelChoiceField(required=False, queryset=ProductSupplier.get_suppliers())


class MyOrderFilterForm(forms.Form):
    order_number = forms.CharField(required=False)
    transaction_id = forms.CharField(required=False)
    item_id = forms.IntegerField(required=False)


class PayoutFilterForm(OrderFilterForm):
    STATUSES = [('', '---------')] + Payout.STATUSES

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
    label_size = forms.ModelMultipleChoiceField(required=False, queryset=LabelSize.objects.all().order_by('size'),
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
    supplier = forms.ModelChoiceField(required=False, queryset=ProductSupplier.get_suppliers())
    cancelled = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super(LineFilterForm, self).__init__(*args, **kwargs)
        try:
            self.fields['product_sku'].choices = [(p.shipstation_sku, f"{p.shipstation_sku} {p.title}") for p in PLSupplement.objects.all()]
        except:
            self.fields['product_sku'].choices = []

        if self.fields['product_sku'].choices:
            self.fields['product_sku'].choices.sort(key=self.sort_key)

    def sort_key(self, values):
        return [int(element) if element.isdigit() else element
                for element in re.split("([0-9]+)", values[0])]


class LabelFilterForm(forms.Form):
    STATUSES = [i for i in UserSupplementLabel.LABEL_STATUSES
                if i[0] != 'draft']

    status = forms.MultipleChoiceField(required=False, choices=STATUSES,
                                       widget=forms.SelectMultiple(
                                           attrs={'id': 'id_label_sku_filter', 'data-placeholder': 'Select label status'}))
    sku = forms.CharField(required=False)


class AllLabelFilterForm(forms.Form):
    SORT_STATUSES = [
        ('newest', 'Newest Labels First'),
        ('oldest', 'Oldest Labels First'),
    ]
    SUPPLEMENT_STATUSES = [
        ('', '---------'),
        ('read', 'Read'),
        ('unread', 'Unread'),
    ]

    label_user_name = forms.CharField(required=False)
    product_sku = forms.MultipleChoiceField(required=False,
                                            widget=forms.SelectMultiple(attrs={
                                                'id': 'id_product_supplement_sku',
                                                'data-placeholder': 'Select product sku'}))
    title = forms.CharField(required=False)
    sort = forms.ChoiceField(required=False, choices=SORT_STATUSES)
    comments_status = forms.ChoiceField(required=False, choices=SUPPLEMENT_STATUSES)
    supplier = forms.ModelChoiceField(required=False, queryset=ProductSupplier.get_suppliers())

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        try:
            self.fields['product_sku'].choices = [(p.shipstation_sku, f"{p.shipstation_sku} {p.title}")
                                                  for p in PLSupplement.objects.all()]
        except:
            self.fields['product_sku'].choices = []

        if self.fields['product_sku'].choices:
            self.fields['product_sku'].choices.sort(key=self.sort_key)

    def sort_key(self, values):
        return [int(element) if element.isdigit() else element
                for element in re.split("([0-9]+)", values[0])]


class BillingForm(forms.Form):
    name = forms.CharField()
    cc_number = forms.CharField(max_length=16)
    cc_expiry = forms.CharField()
    cc_cvv = forms.CharField(max_length=4)
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
            'shipping',
        ]
        widgets = {
            'amount': forms.HiddenInput(),
            'order_shipped': forms.HiddenInput(),
            'description': forms.Textarea(attrs={'rows': 1})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['amount'].required = False
        self.fields['description'].required = False
        self.fields['fee'].required = False
        self.fields['shipping'].required = False


class ShippingCostsWidget(forms.Textarea):
    template_name = 'supplements/widgets/shipping_cost.html'

    class Media:
        css = {
            'all': ('pls/css/widgets/shipping_cost.css',)
        }
        js = ('pls/js/widgets/shipping_cost.js',)


class ShippingGroupAdminForm(forms.ModelForm):
    data = forms.CharField(widget=ShippingCostsWidget)
