from django import forms

from .models import Order, Payout, Product


class ProductBaseForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['title',
                  'description',
                  'category',
                  'tags',
                  'shipstation_sku',
                  'cost_price',
                  ]

        widgets = {
            'tags': forms.TextInput(),
        }


class ProductForm(ProductBaseForm):
    product_image = forms.ImageField()


class ProductEditForm(ProductBaseForm):
    product_image = forms.ImageField(required=False)


class OrderFilterForm(forms.Form):
    STATUSES = [('', '-')] + Order.STATUSES

    order_number = forms.CharField(required=False)
    status = forms.ChoiceField(required=False, choices=STATUSES)
    email = forms.CharField(required=False)
    amount = forms.DecimalField(required=False)
    date = forms.DateField(required=False)


class PayoutFilterForm(OrderFilterForm):
    STATUSES = [('', '-')] + Payout.STATUSES

    status = forms.ChoiceField(required=False, choices=STATUSES)
