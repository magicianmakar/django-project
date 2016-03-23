from django.db import models
from django import forms

from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.forms.utils import ErrorList

# for login with email
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.forms import ValidationError


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
    plan_registration = None

    def __init__(self, *args, **kwargs):
        super(RegisterForm, self).__init__(*args, **kwargs)
        self.error_class = BsErrorList

    def clean_username(self):
        if '@' in self.cleaned_data["username"]:
            raise forms.ValidationError('@ is not allowed in username')

        return self.cleaned_data["username"]

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


class UserProfileEmailForm(forms.Form):
    password = forms.CharField(label='Current Password')
    email = forms.EmailField(max_length=254)

    password1 = forms.CharField(label='New Password', min_length=8, required=False)
    password2 = forms.CharField(label='Confirm Password', min_length=8, required=False)

    def __init__(self, user, data=None):
        self.user = user
        super(UserProfileEmailForm, self).__init__(data=data)

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
        if '@' in username:
            try:
                username = User.objects.get(email__iexact=username).username
            except (ObjectDoesNotExist, MultipleObjectsReturned):
                print 'WARNING: LOGIN EXCEPTION: {}'.format(username)

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
