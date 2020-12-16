from django import forms

from product_common.lib.views import upload_image_to_aws
from addons_core.utils import DictAsObject
from .models import Step


class URLFileInputWidget(forms.ClearableFileInput):
    template_name = 'addons/widgets/url_file_input.html'

    def is_initial(self, value):
        return bool(value)

    def format_value(self, value):
        return super().format_value(DictAsObject({'url': value}))


class StepForm(forms.ModelForm):
    icon_src = forms.FileField(required=False, widget=URLFileInputWidget())
    request = None

    def _upload_icon(self, field_name, folder_name):
        icon = self.cleaned_data[field_name]
        if icon and not isinstance(icon, str):
            return upload_image_to_aws(icon, folder_name, self.request.user.id)
        return icon

    def clean_icon_src(self):
        if self.request.POST.get('icon_src_url_clear'):
            return ''
        return self._upload_icon('icon_src', 'goals_step')

    class Meta:
        model = Step
        exclude = ('users',)
