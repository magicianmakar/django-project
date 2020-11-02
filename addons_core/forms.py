import re
from urllib.parse import parse_qs, urlparse

from ckeditor_uploader.widgets import CKEditorUploadingWidget
from django import forms

from lib.exceptions import capture_exception
from product_common.lib.views import upload_image_to_aws
from .models import Addon, AddonPrice
from .utils import DictAsObject


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


class URLFileInput(forms.ClearableFileInput):
    def is_initial(self, value):
        return bool(value)

    def format_value(self, value):
        return super().format_value(DictAsObject({'url': value}))


class AddonForm(forms.ModelForm):
    description = forms.CharField(widget=CKEditorUploadingWidget(config_name='addons_ckeditor'))
    faq = forms.CharField(widget=CKEditorUploadingWidget(config_name='addons_ckeditor'))
    icon_url = forms.FileField(widget=URLFileInput())
    banner_url = forms.FileField(widget=URLFileInput())

    request = None

    def _upload_icon(self, field_name, folder_name):
        icon = self.cleaned_data[field_name]
        if icon and not isinstance(icon, str):
            return upload_image_to_aws(icon, folder_name, self.request.user.id)
        return icon

    def clean_banner_url(self):
        return self._upload_icon('banner_url', 'addon_banners')

    def clean_icon_url(self):
        return self._upload_icon('icon_url', 'addon_icons')

    def clean_youtube_url(self):
        youtube_id = None
        youtube_url = self.cleaned_data['youtube_url'] or ''
        if youtube_url:
            youtube_id = re.findall('youtube.com/embed/[^?#]+', youtube_url)
            if youtube_id:
                youtube_id = youtube_id.pop().split('/').pop()

        if not youtube_id:
            try:
                youtube_id = parse_qs(urlparse(youtube_url).query)['v'].pop()
            except KeyError:
                youtube_id = urlparse(youtube_url).path.strip('/')
            except:
                capture_exception(level='warning')

        return f'https://www.youtube.com/embed/{youtube_id}' if youtube_id else ''

    def clean_vimeo_url(self):
        vimeo_id = None
        vimeo_url = self.cleaned_data['vimeo_url'] or ''
        if vimeo_url:
            vimeo_id = re.findall('player.vimeo.com/video/[^?#]+', vimeo_url)
            if vimeo_id:
                vimeo_id = vimeo_id.pop().split('/').pop()

        if not vimeo_id:
            try:
                vimeo_id = urlparse(vimeo_url).path.strip('/')
            except:
                capture_exception(level='warning')

        return f'https://player.vimeo.com/video/{vimeo_id}' if vimeo_id else ''

    class Meta:
        model = Addon
        exclude = []


class AddonPriceAdminForm(forms.ModelForm):
    price = HiddenReadonlyField(can_edit=False, required=False)
    stripe_price_id = HiddenReadonlyField(can_create=False, required=False)

    class Meta:
        model = AddonPrice
        exclude = []
