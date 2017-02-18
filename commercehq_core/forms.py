from django.forms import ModelForm

from .models import CommerceHQStore


class CommerceHQStoreForm(ModelForm):
    class Meta:
        model = CommerceHQStore
        fields = 'url', 'title', 'api_key', 'api_password'
