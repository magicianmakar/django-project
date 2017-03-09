import re

from django import forms
from django.forms import ModelForm

from .models import CommerceHQStore, CommerceHQBoard


class CommerceHQStoreForm(ModelForm):
    api_url = forms.URLField(max_length=512)

    class Meta:
        model = CommerceHQStore
        fields = 'api_url', 'title', 'api_key', 'api_password'

    def clean_api_url(self):
        url = self.cleaned_data['api_url']
        url = re.findall(r'([^/.]+\.commercehq(?:dev)?\.com)', url)

        if not len(url):
            raise forms.ValidationError('Only CommerceHQ stores can be added.')

        return 'https://{}'.format(url.pop())


class CommerceHQBoardForm(ModelForm):
    class Meta:
        model = CommerceHQBoard
        fields = 'title',
