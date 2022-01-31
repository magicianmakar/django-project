from django import forms

from addons_core.forms import URLFileInputWidget
from product_common.lib.views import upload_image_to_aws


class ApplicationMenuItemForm(forms.ModelForm):
    icon_url = forms.FileField(required=False, widget=URLFileInputWidget())
    request = None

    def clean_icon_url(self):
        if self.request.POST.get('icon_url_url_clear'):
            return ''

        icon = self.cleaned_data['icon_url']
        if icon and not isinstance(icon, str):
            return upload_image_to_aws(icon, 'app_menu_icons', self.request.user.id)
        return icon
