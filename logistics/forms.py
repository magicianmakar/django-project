from django import forms

from .models import Carrier, Warehouse, Package


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        exclude = []


class CarrierForm(forms.ModelForm):
    class Meta:
        model = Carrier
        exclude = []


class AdminCarrierForm(forms.ModelForm):
    class Meta:
        model = Carrier
        exclude = ['source_id']


class OrderAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['warehouse'].queryset = Warehouse.objects.filter(user=self.instance.warehouse.user.models_user)
        self.fields['package'].queryset = Package.objects.filter(user=self.instance.warehouse.user.models_user)
