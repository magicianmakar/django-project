from django import forms

from leadgalaxy.models import (
    UserProfile,
    SubuserPermission,
    SubuserCHQPermission,
    SubuserWooPermission,
    SubuserGKartPermission,
    SubuserBigCommercePermission,
    SubuserFBPermission,
    SubuserGooglePermission,
)
from leadgalaxy.signals import add_fb_store_permissions_base
from leadgalaxy.signals import add_google_store_permissions_base


class SubUserStoresForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["subuser_stores", "subuser_chq_stores", "subuser_woo_stores", "subuser_gkart_stores",
                  "subuser_bigcommerce_stores", "subuser_fb_stores", "subuser_google_stores"]

    def __init__(self, *args, **kwargs):
        parent_user = kwargs.pop("parent_user")
        super(SubUserStoresForm, self).__init__(*args, **kwargs)

        # Taken from http://stackoverflow.com/a/2264722/3896300
        if kwargs.get('instance'):
            initial = kwargs.setdefault('initial', {})
            initial['subuser_stores'] = [t.pk for t in kwargs['instance'].subuser_stores.all()]
            initial['subuser_chq_stores'] = [t.pk for t in kwargs['instance'].subuser_chq_stores.all()]
            initial['subuser_woo_stores'] = [t.pk for t in kwargs['instance'].subuser_woo_stores.all()]
            initial['subuser_gkart_stores'] = [t.pk for t in kwargs['instance'].subuser_gkart_stores.all()]
            initial['subuser_bigcommerce_stores'] = [t.pk for t in kwargs['instance'].subuser_bigcommerce_stores.all()]
            initial['subuser_fb_stores'] = [t.pk for t in kwargs['instance'].subuser_fb_stores.all()]
            initial['subuser_google_stores'] = [t.pk for t in kwargs['instance'].subuser_google_stores.all()]

        self.fields["subuser_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_stores"].help_text = ""
        self.fields["subuser_stores"].queryset = parent_user.profile.get_shopify_stores()

        self.fields["subuser_chq_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_chq_stores"].help_text = ""
        self.fields["subuser_chq_stores"].queryset = parent_user.profile.get_chq_stores()

        self.fields["subuser_woo_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_woo_stores"].help_text = ""
        self.fields["subuser_woo_stores"].queryset = parent_user.profile.get_woo_stores()

        self.fields["subuser_gkart_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_gkart_stores"].help_text = ""
        self.fields["subuser_gkart_stores"].queryset = parent_user.profile.get_gkart_stores()

        self.fields["subuser_bigcommerce_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_bigcommerce_stores"].help_text = ""
        self.fields["subuser_bigcommerce_stores"].queryset = parent_user.profile.get_bigcommerce_stores()

        self.fields["subuser_fb_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_fb_stores"].help_text = ""
        self.fields["subuser_fb_stores"].queryset = parent_user.profile.get_fb_stores()

        self.fields["subuser_google_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_google_stores"].help_text = ""
        self.fields["subuser_google_stores"].queryset = parent_user.profile.get_google_stores()

    def save(self, commit=True):
        instance = forms.ModelForm.save(self, False)

        old_save_m2m = self.save_m2m

        def save_m2m():
            old_save_m2m()
            instance.subuser_stores.clear()
            for store in self.cleaned_data['subuser_stores']:
                instance.subuser_stores.add(store)

            instance.subuser_chq_stores.clear()
            for store in self.cleaned_data['subuser_chq_stores']:
                instance.subuser_chq_stores.add(store)

            instance.subuser_woo_stores.clear()
            for store in self.cleaned_data['subuser_woo_stores']:
                instance.subuser_woo_stores.add(store)

            instance.subuser_gkart_stores.clear()
            for store in self.cleaned_data['subuser_gkart_stores']:
                instance.subuser_gkart_stores.add(store)

            instance.subuser_bigcommerce_stores.clear()
            for store in self.cleaned_data['subuser_bigcommerce_stores']:
                instance.subuser_bigcommerce_stores.add(store)

            instance.subuser_fb_stores.clear()
            for store in self.cleaned_data['subuser_fb_stores']:
                instance.subuser_fb_stores.add(store)

            instance.subuser_google_stores.clear()
            for store in self.cleaned_data['subuser_google_stores']:
                instance.subuser_google_stores.add(store)

        self.save_m2m = save_m2m

        if commit:
            instance.save()
            self.save_m2m()

        return instance


class SubuserPermissionsChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return obj.name


class SubuserPermissionsCheckboxFieldRenderer(forms.widgets.CheckboxSelectMultiple):
    outer_html = '<ul{id_attr} class="list-unstyled">{content}</ul>'


class SubuserPermissionsSelectMultiple(forms.widgets.CheckboxSelectMultiple):
    renderer = SubuserPermissionsCheckboxFieldRenderer


class SubuserPermissionsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(SubuserPermissionsForm, self).__init__(*args, **kwargs)
        permissions_initial = kwargs['initial']['permissions']
        permissions_queryset = SubuserPermission.objects.filter(store=kwargs['initial']['store'])
        permissions_widget = SubuserPermissionsSelectMultiple(attrs={'class': 'js-switch'})
        permissions_field = SubuserPermissionsChoiceField(initial=permissions_initial,
                                                          queryset=permissions_queryset,
                                                          widget=permissions_widget,
                                                          required=False)
        self.fields['permissions'] = permissions_field


class SubuserCHQPermissionsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(SubuserCHQPermissionsForm, self).__init__(*args, **kwargs)
        permissions_initial = kwargs['initial']['permissions']
        permissions_queryset = SubuserCHQPermission.objects.filter(store=kwargs['initial']['store'])
        permissions_widget = SubuserPermissionsSelectMultiple(attrs={'class': 'js-switch'})
        permissions_field = SubuserPermissionsChoiceField(initial=permissions_initial,
                                                          queryset=permissions_queryset,
                                                          widget=permissions_widget,
                                                          required=False)
        self.fields['permissions'] = permissions_field


class SubuserWooPermissionsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(SubuserWooPermissionsForm, self).__init__(*args, **kwargs)
        permissions_initial = kwargs['initial']['permissions']
        permissions_queryset = SubuserWooPermission.objects.filter(store=kwargs['initial']['store'])
        permissions_widget = SubuserPermissionsSelectMultiple(attrs={'class': 'js-switch'})
        permissions_field = SubuserPermissionsChoiceField(initial=permissions_initial,
                                                          queryset=permissions_queryset,
                                                          widget=permissions_widget,
                                                          required=False)
        self.fields['permissions'] = permissions_field


class SubuserGKartPermissionsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(SubuserGKartPermissionsForm, self).__init__(*args, **kwargs)
        permissions_initial = kwargs['initial']['permissions']
        permissions_queryset = SubuserGKartPermission.objects.filter(store=kwargs['initial']['store'])
        permissions_widget = SubuserPermissionsSelectMultiple(attrs={'class': 'js-switch'})
        permissions_field = SubuserPermissionsChoiceField(initial=permissions_initial,
                                                          queryset=permissions_queryset,
                                                          widget=permissions_widget,
                                                          required=False)
        self.fields['permissions'] = permissions_field


class SubuserBigCommercePermissionsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(SubuserBigCommercePermissionsForm, self).__init__(*args, **kwargs)
        permissions_initial = kwargs['initial']['permissions']
        permissions_queryset = SubuserBigCommercePermission.objects.filter(store=kwargs['initial']['store'])
        permissions_widget = SubuserPermissionsSelectMultiple(attrs={'class': 'js-switch'})
        permissions_field = SubuserPermissionsChoiceField(initial=permissions_initial,
                                                          queryset=permissions_queryset,
                                                          widget=permissions_widget,
                                                          required=False)
        self.fields['permissions'] = permissions_field


class SubuserFBPermissionsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(SubuserFBPermissionsForm, self).__init__(*args, **kwargs)
        permissions_initial = kwargs['initial']['permissions']
        store = kwargs['initial']['store']
        permissions_queryset = SubuserFBPermission.objects.filter(store=store)

        # Handle Facebook stores that were created before subusers functionality was implemented
        if not permissions_queryset:
            add_fb_store_permissions_base(store=store)

        permissions_widget = SubuserPermissionsSelectMultiple(attrs={'class': 'js-switch'})
        permissions_field = SubuserPermissionsChoiceField(initial=permissions_initial,
                                                          queryset=permissions_queryset,
                                                          widget=permissions_widget,
                                                          required=False)
        self.fields['permissions'] = permissions_field


class SubuserGooglePermissionsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(SubuserGooglePermissionsForm, self).__init__(*args, **kwargs)
        permissions_initial = kwargs['initial']['permissions']
        store = kwargs['initial']['store']
        permissions_queryset = SubuserGooglePermission.objects.filter(store=store)

        # Handle Google stores that were created before subusers functionality was implemented
        if not permissions_queryset:
            add_google_store_permissions_base(store=store)

        permissions_widget = SubuserPermissionsSelectMultiple(attrs={'class': 'js-switch'})
        permissions_field = SubuserPermissionsChoiceField(initial=permissions_initial,
                                                          queryset=permissions_queryset,
                                                          widget=permissions_widget,
                                                          required=False)
        self.fields['permissions'] = permissions_field
