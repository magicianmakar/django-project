from django import forms

from .models import Carrier, Warehouse


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
