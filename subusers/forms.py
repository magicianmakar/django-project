from django import forms

from leadgalaxy.models import UserProfile, SubuserPermission, SubuserCHQPermission, SubuserWooPermission, SubuserGearPermission


class SubUserStoresForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["subuser_stores", "subuser_chq_stores", "subuser_woo_stores", "subuser_gear_stores"]

    def __init__(self, *args, **kwargs):
        parent_user = kwargs.pop("parent_user")
        super(SubUserStoresForm, self).__init__(*args, **kwargs)

        # Taken from http://stackoverflow.com/a/2264722/3896300
        if kwargs.get('instance'):
            initial = kwargs.setdefault('initial', {})
            initial['subuser_stores'] = [t.pk for t in kwargs['instance'].subuser_stores.all()]
            initial['subuser_chq_stores'] = [t.pk for t in kwargs['instance'].subuser_chq_stores.all()]
            initial['subuser_woo_stores'] = [t.pk for t in kwargs['instance'].subuser_woo_stores.all()]
            initial['subuser_gear_stores'] = [t.pk for t in kwargs['instance'].subuser_gear_stores.all()]

        self.fields["subuser_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_stores"].help_text = ""
        self.fields["subuser_stores"].queryset = parent_user.profile.get_shopify_stores()

        self.fields["subuser_chq_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_chq_stores"].help_text = ""
        self.fields["subuser_chq_stores"].queryset = parent_user.profile.get_chq_stores()

        self.fields["subuser_woo_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_woo_stores"].help_text = ""
        self.fields["subuser_woo_stores"].queryset = parent_user.profile.get_woo_stores()

        self.fields["subuser_gear_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_gear_stores"].help_text = ""
        self.fields["subuser_gear_stores"].queryset = parent_user.profile.get_gear_stores()

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

            instance.subuser_gear_stores.clear()
            for store in self.cleaned_data['subuser_gear_stores']:
                instance.subuser_gear_stores.add(store)

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


class SubuserGearPermissionsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(SubuserGearPermissionsForm, self).__init__(*args, **kwargs)
        permissions_initial = kwargs['initial']['permissions']
        permissions_queryset = SubuserGearPermission.objects.filter(store=kwargs['initial']['store'])
        permissions_widget = SubuserPermissionsSelectMultiple(attrs={'class': 'js-switch'})
        permissions_field = SubuserPermissionsChoiceField(initial=permissions_initial,
                                                          queryset=permissions_queryset,
                                                          widget=permissions_widget,
                                                          required=False)
        self.fields['permissions'] = permissions_field
