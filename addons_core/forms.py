from django import forms

from .models import AddonPrice


class HiddenReadonlyWidget(forms.TextInput):
    template_name = 'addons/widgets/hidden_readonly.html'

    def __init__(self, can_edit, can_create, *args, **kwargs):
        self.can_edit = can_edit
        self.can_create = can_create
        super().__init__(*args, **kwargs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['can_edit'] = self.can_edit
        context['can_create'] = self.can_create
        return context


class HiddenReadonlyField(forms.CharField):
    def __init__(self, can_edit=True, can_create=True, **kwargs):
        kwargs['widget'] = HiddenReadonlyWidget(can_edit, can_create)
        super().__init__(**kwargs)

    def has_changed(self, initial, data):
        if initial and not self.widget.can_edit:
            self.disabled = True
            return False
        elif not initial and not self.widget.can_create:
            self.disabled = True
            return False

        return super().has_changed(initial, data)


class AddonPriceAdminForm(forms.ModelForm):
    price = HiddenReadonlyField(can_edit=False, required=False)
    stripe_price_id = HiddenReadonlyField(can_create=False, required=False)

    class Meta:
        model = AddonPrice
        exclude = []
