from django.db import models
from django import forms

from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.forms.utils import ErrorList

# for login with email
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.forms import ValidationError

from .models import UserProfile
from .utils import login_attempts_exceeded, unlock_account_email


class BsErrorList(ErrorList):
    def __unicode__(self):
        return self.as_divs()

    def as_divs(self):
        if not self:
            return u''
        return u'%s' % ''.join([u'<div class="has-error"><label class="control-label" style="text-align: left">%s</label></div>' % e.rstrip('.')
                                for e in self])


class RegisterForm(UserCreationForm):
    email = forms.EmailField()
    accept_terms = forms.BooleanField(required=False)
    plan_registration = None

    def __init__(self, *args, **kwargs):
        super(RegisterForm, self).__init__(*args, **kwargs)
        self.error_class = BsErrorList

    def clean_username(self):
        try:

            assert '@' not in self.cleaned_data["username"], '@ is not allowed in username'
            assert len(self.cleaned_data["username"]) >= 5, 'Username should be at least 5 characters'

            User.objects.get(username__iexact=self.cleaned_data["username"])

            raise forms.ValidationError('Username is already registred to an other account.')
        except ObjectDoesNotExist:
            return self.cleaned_data["username"]
        except AssertionError as e:
            raise forms.ValidationError(e.message)
        except Exception as e:
            raise forms.ValidationError('Username is already registred to an other account.')
            print 'WARNING: Register Form Exception: {}'.format(repr(e))

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
        raise forms.ValidationError(
            'A user with that email already exists',
            code='duplicate_email',
        )

    def clean_accept_terms(self):
        terms_accpeted = self.cleaned_data.get("accept_terms", False)
        if not terms_accpeted:
            raise forms.ValidationError("You need to accept Terms & Conditions")
        return terms_accpeted

    def save(self, commit=True):
        user = super(RegisterForm, self).save(commit=False)
        user.email = self.cleaned_data["email"]

        if commit:
            user.save()

        return user

    def set_plan_registration(self, plan):
        self.plan_registration = plan


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

    invoice_to_company = forms.BooleanField(required=False)


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
        username = self.data['username']
        if login_attempts_exceeded(username):
            unlock_email = unlock_account_email(username)

            from raven.contrib.django.raven_compat.models import client as raven_client
            raven_client.captureMessage('Maximum login attempts reached',
                                        extra={'username': username, 'from': 'WebApp', 'unlock_email': unlock_email},
                                        level='warning')

            raise ValidationError(
                "You have reached the maximum login attempts. Please try again later.",
                code='invalid_login',
                params={'username': self.username_field.verbose_name},
            )

        email_login = '@' in username
        try:
            if email_login:
                return User.objects.get(email__iexact=username).username
            else:
                return User.objects.get(username__iexact=username).username

        except ObjectDoesNotExist as e:
            raise ValidationError(
                "The {} you've entered doesn't match any account.".format('Email' if email_login else 'Username'),
                code='invalid_login',
                params={'username': self.username_field.verbose_name},
            )
        except Exception as e:
            print 'WARNING: LOGIN EXCEPTION: {} For {}'.format(repr(e), username)

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
        fields = ["subuser_stores"]

    def __init__(self, *args, **kwargs):
        parent_user = kwargs.pop("parent_user")
        super(SubUserStoresForm, self).__init__(*args, **kwargs)

        # Taken from http://stackoverflow.com/a/2264722/3896300
        if kwargs.get('instance'):
            initial = kwargs.setdefault('initial', {})
            initial['subuser_stores'] = [t.pk for t in kwargs['instance'].subuser_stores.all()]

        self.fields["subuser_stores"].widget = forms.widgets.CheckboxSelectMultiple()
        self.fields["subuser_stores"].help_text = ""
        self.fields["subuser_stores"].queryset = parent_user.profile.get_active_stores()

    def save(self, commit=True):
        instance = forms.ModelForm.save(self, False)

        old_save_m2m = self.save_m2m

        def save_m2m():
            old_save_m2m()
            instance.subuser_stores.clear()
            for store in self.cleaned_data['subuser_stores']:
                instance.subuser_stores.add(store)

        self.save_m2m = save_m2m

        if commit:
            instance.save()
            self.save_m2m()

        return instance
