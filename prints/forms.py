# f'uploads/layerapp/product/{obj.source_id}.{extension}'
from django import forms

from .models import Product


class TextImageWidget(forms.ClearableFileInput):
    template_name = 'prints/partial/admin_text_image_widget.html'

    def is_initial(self, value):
        return bool(value)

    def clear_checkbox_name(self, name):
        return name + '-clear'


class ProductForm(forms.ModelForm):

    class Meta:
        model = Product
        fields = ('__all__')
        widgets = {
            'dropified_image': TextImageWidget(),
        }
