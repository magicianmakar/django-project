from django import forms

from django.contrib.auth.models import User
from django.forms.utils import ErrorList

# for login with email
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import validate_email, ValidationError

from .models import UserProfile, SubuserPermission, SubuserCHQPermission, SubuserWooPermission
from shopified_core.utils import login_attempts_exceeded, unlock_account_email, unique_username

from raven.contrib.django.raven_compat.models import client as raven_client


class BsErrorList(ErrorList):
    def __unicode__(self):
        return self.as_divs()

    def as_divs(self):
        if not self:
            return u''
        return u'%s' % ''.join([u'<div class="has-error"><label class="control-label" style="text-align: left">%s</label></div>' % e.rstrip('.')
                                for e in self])


class RegisterForm(forms.ModelForm):
    fullname = forms.CharField(required=False)
    email = forms.EmailField()
    accept_terms = forms.BooleanField(required=False)

    error_messages = {
        'password_mismatch': "The two password fields didn't match.",
    }

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput)

    password2 = forms.CharField(
        label="Password confirmation",
        widget=forms.PasswordInput,
        help_text="Enter the same password as above, for verification.")

    plan_registration = None

    class Meta:
        model = User
        fields = ()

    def __init__(self, *args, **kwargs):
        super(RegisterForm, self).__init__(*args, **kwargs)
        self.error_class = BsErrorList

    def set_plan_registration(self, plan):
        self.plan_registration = plan

    def clean_fullname(self):
        name = self.cleaned_data["fullname"]
        return name.title().strip() if name else ''

    def clean_username(self):
        try:
            return unique_username(self.clean_email(), fullname=self.clean_fullname())

        except AssertionError as e:
            raise forms.ValidationError(e.message)
        except Exception as e:
            raven_client.captureException()
            raise forms.ValidationError('Username is already registred to an other account.')

        raise forms.ValidationError('Username is already registred to an other account.')

    def clean_email(self):
        email = self.cleaned_data["email"]

        if self.plan_registration and self.plan_registration.email:
            if email != self.plan_registration.email:
                raise forms.ValidationError(
                    'Email is different than the purshase email',
                    code='duplicate_email',
                )
        try:
            User._default_manager.get(email__iexact=email)
        except User.DoesNotExist:
            return email
        except User.MultipleObjectsReturned:
            pass

        raise forms.ValidationError(
            'A user with that email already exists',
            code='duplicate_email',
        )

    def clean_accept_terms(self):
        terms_accpeted = self.cleaned_data.get("accept_terms", False)
        if not terms_accpeted:
            raise forms.ValidationError("You need to accept Terms & Conditions")
        return terms_accpeted

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(
                self.error_messages['password_mismatch'],
                code='password_mismatch',
            )
        return password2

    def save(self, commit=True):
        user = super(RegisterForm, self).save(commit=False)

        fullname = self.cleaned_data['fullname'].split(' ')
        username = unique_username(self.cleaned_data["email"], fullname=fullname)

        if len(fullname):
            user.first_name = fullname[0]
            user.last_name = u' '.join(fullname[1:])

        user.username = username
        user.email = self.cleaned_data["email"]
        user.set_password(self.cleaned_data["password1"])

        if commit:
            user.save()

        return user


class UserProfileForm(forms.Form):
    first_name = forms.CharField(required=False, max_length=140)
    last_name = forms.CharField(required=False, max_length=140)

    country = forms.CharField(required=False, max_length=10)
    timezone = forms.CharField(required=False, max_length=64)

    company_name = forms.CharField(max_length=100, required=False)
    company_address_line1 = forms.CharField(max_length=255, required=False)
    company_address_line2 = forms.CharField(max_length=255, required=False)
    company_city = forms.CharField(max_length=100, required=False)
    company_state = forms.CharField(max_length=100, required=False)
    company_country = forms.CharField(max_length=100, required=False)
    company_zip_code = forms.CharField(max_length=100, required=False)

    vat = forms.CharField(max_length=100, required=False)
    invoice_to_company = forms.BooleanField(required=False)
    use_relative_dates = forms.BooleanField(required=False)


class UserProfileEmailForm(forms.Form):
    password = forms.CharField(label='Current Password')
    email = forms.EmailField(max_length=254)

    password1 = forms.CharField(label='New Password', min_length=8, required=False)
    password2 = forms.CharField(label='Confirm Password', min_length=8, required=False)

    def __init__(self, user, data=None):
        self.user = user
        super(UserProfileEmailForm, self).__init__(data=data)

    def clean_email(self):
        email = self.cleaned_data["email"]

        try:
            if self.user == User._default_manager.get(email__iexact=email):
                return email
        except User.DoesNotExist:
            return email

        except User.MultipleObjectsReturned:
            pass

        raise forms.ValidationError(
            'A user with that email already exists',
            code='duplicate_email',
        )

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if not self.user.check_password(password):
            raise forms.ValidationError('Invalid Current Password')

        return password

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(
                'The two password fields didn\'t match.',
                code='password_mismatch',
            )

        return password2


class EmailAuthenticationForm(AuthenticationForm):
    def clean_username(self):

        try:
            username = self.data['username'].strip()

            validate_email(username)
        except:
            raven_client.captureException()
            raise

        if login_attempts_exceeded(username):
            unlock_email = unlock_account_email(username)

            raven_client.captureMessage('Maximum login attempts reached',
                                        extra={'username': username, 'from': 'WebApp', 'unlock_email': unlock_email},
                                        level='warning')

            raise ValidationError(
                "You have reached the maximum login attempts. Please try again later.",
                code='invalid_login',
                params={'username': self.username_field.verbose_name},
            )

        try:
            return User.objects.get(email__iexact=username, profile__shopify_app_store=False).username

        except ObjectDoesNotExist:
            raise ValidationError(
                "The Email you've entered doesn't match any account.",
                code='invalid_login',
                params={'username': self.username_field.verbose_name},
            )

        except:
            raven_client.captureException()

            raise ValidationError(
                self.error_messages['invalid_login'],
                code='invalid_login',
                params={'username': self.username_field.verbose_name},
            )

        return username


class EmailForm(forms.Form):
    email = forms.EmailField()

    def __init__(self, *args, **kwargs):
        super(EmailForm, self).__init__(*args, **kwargs)
        self.error_class = BsErrorList


class SubUserStoresForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["subuser_stores", "subuser_chq_stores", "subuser_woo_stores"]

    def __init__(self, *args, **kwargs):
        parent_user = kwargs.pop("parent_user")
        super(SubUserStoresForm, self).__init__(*args, **kwargs)

        # Taken from http://stackoverflow.com/a/2264722/3896300
        if kwargs.get('instance'):
            initial = kwargs.setdefault('initial', {})
            initial['subuser_stores'] = [t.pk for t in kwargs['instance'].subuser_stores.all()]
            initial['subuser_chq_stores'] = [t.pk for t in kwargs['instance'].subuser_chq_stores.all()]
            initial['subuser_woo_stores'] = [t.pk for t in kwargs['instance'].subuser_woo_stores.all()]

        self.fields["subuser_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_stores"].help_text = ""
        self.fields["subuser_stores"].queryset = parent_user.profile.get_shopify_stores()

        self.fields["subuser_chq_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_chq_stores"].help_text = ""
        self.fields["subuser_chq_stores"].queryset = parent_user.profile.get_chq_stores()

        self.fields["subuser_woo_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_woo_stores"].help_text = ""
        self.fields["subuser_woo_stores"].queryset = parent_user.profile.get_woo_stores()

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
