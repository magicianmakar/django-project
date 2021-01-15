import re
import json
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


class URLFileInputWidget(forms.ClearableFileInput):
    template_name = 'addons/widgets/url_file_input.html'

    def is_initial(self, value):
        return bool(value)

    def format_value(self, value):
        return super().format_value(DictAsObject({'url': value}))


class KeyBenefitsWidget(forms.TextInput):
    template_name = 'addons/widgets/key_benefits.html'

    class Media:
        css = {
            'all': ('addons/css/widgets/key-benefits.css',)
        }
        js = ('addons/js/widgets/key-benefits.js',)

    def is_initial(self, value):
        return bool(value)

    def format_value(self, value):
        if not value:
            value = '[{}]'

        return super().format_value(value)


class AddonForm(forms.ModelForm):
    STORE_CHOICES = (
        ('bigcommerce', 'BigCommerce'),
        ('chq', 'CommerceHQ'),
        ('gkart', 'GrooveKart'),
        ('shopify', 'Shopify'),
        ('woo', 'WooCommerce')
    )
    description = forms.CharField(required=False, widget=CKEditorUploadingWidget(config_name='addons_ckeditor'))
    store_types = forms.MultipleChoiceField(choices=STORE_CHOICES, required=False, widget=forms.CheckboxSelectMultiple)
    faq = forms.CharField(required=False, widget=CKEditorUploadingWidget(config_name='addons_ckeditor'))
    icon_url = forms.FileField(required=False, widget=URLFileInputWidget())
    banner_url = forms.FileField(required=False, widget=URLFileInputWidget())
    key_benefits = forms.CharField(required=False, widget=KeyBenefitsWidget())
    request = None

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance', None)
        if instance is not None:
            store_list = [value for value, label in self.STORE_CHOICES if label in instance.store_types.split(',')]
            instance.store_types = store_list
        super().__init__(*args, **kwargs)

    def _upload_icon(self, field_name, folder_name):
        icon = self.cleaned_data[field_name]
        if icon and not isinstance(icon, str):
            return upload_image_to_aws(icon, folder_name, self.request.user.id)
        return icon

    def clean_banner_url(self):
        if self.request.POST.get('banner_url_url_clear'):
            return ''
        return self._upload_icon('banner_url', 'addon_banners')

    def clean_icon_url(self):
        if self.request.POST.get('icon_url_url_clear'):
            return ''
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

    def clean_key_benefits(self):
        count = len(self.request.POST.getlist('key_benefits_count'))
        index = -1
        benefits = []
        while count > 0:
            index += 1
            if f'key_benefits_title_{index}' not in self.request.POST:
                continue

            key_benefit = {
                'title': self.request.POST[f'key_benefits_title_{index}'],
                'description': self.request.POST[f'key_benefits_description_{index}'],
                'banner': self.request.POST.get(f'key_benefits_banner_{index}', ''),
            }

            if self.request.POST.get(f'key_benefits_clear_{index}'):
                key_benefit['banner'] = ''
            elif self.request.FILES.get(f'key_benefits_upload_{index}'):
                key_benefit['banner'] = upload_image_to_aws(
                    self.request.FILES.get(f'key_benefits_upload_{index}'),
                    'addon_benefits',
                    self.request.user.id
                )

            benefits.append(key_benefit)
            count -= 1

        return json.dumps(benefits)

    def clean_store_types(self):
        store_list = [label for value, label in self.fields['store_types'].choices if value in self.cleaned_data['store_types']]
        supported_store_types = ','.join(store_list)
        return supported_store_types

    class Meta:
        model = Addon
        exclude = []


class AddonPriceAdminForm(forms.ModelForm):
    price = HiddenReadonlyField(can_edit=False, required=False)
    stripe_price_id = HiddenReadonlyField(can_create=False, required=False)

    class Meta:
        model = AddonPrice
        exclude = []
