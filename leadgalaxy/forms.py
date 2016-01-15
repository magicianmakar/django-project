from django.db import models
from django import forms

from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.forms.utils import ErrorList

# for login with email
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ObjectDoesNotExist
from django.forms import ValidationError
from django.core.paginator import Paginator

import requests

class BsErrorList(ErrorList):
    def __unicode__(self):
        return self.as_divs()

    def as_divs(self):
        if not self: return u''
        return u'%s' % ''.join([u'<div class="has-error"><label class="control-label" style="text-align: left">%s</label></div>' % e.rstrip('.') \
            for e in self])

class RegisterForm(UserCreationForm):
    email = forms.EmailField()

    def __init__(self, *args, **kwargs):
        super(RegisterForm, self).__init__(*args, **kwargs)
        self.error_class = BsErrorList

    def clean_email(self):
        email = self.cleaned_data["email"]
        try:
            User._default_manager.get(email=email)
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

class EmailAuthenticationForm(AuthenticationForm):
    def clean_username(self):
        username = self.data['username']
        if '@' in username:
            try:
                username = User.objects.get(email=username).username
            except ObjectDoesNotExist:
                raise ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                    params={'username':self.username_field.verbose_name},
                )
        return username

class ShopifyOrderPaginator(Paginator):
    def __init__(self, *args, **kwargs):
        super(ShopifyOrderPaginator, self).__init__(*args, **kwargs)

        self.reverse_order = False

    def set_store(self, store):
        self.store = store

    def set_filter(self, status, fulfillment, financial):
        self.status = status
        self.fulfillment = fulfillment
        self.financial = financial

    def set_order_limit(self, limit):
        self.order_limit = limit

    def set_current_page(self, page):
        self.current_page = page

    def set_reverse_order(self, reverse_order):
        self.reverse_order = reverse_order

        if self.reverse_order:
            pages = range(1, self.num_pages + 1)
            self.reverse_pages = dict(zip(pages, reversed(pages)))

    def page(self, number):
        """
        Returns a Page object for the given 1-based page number.
        """

        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page
        if top + self.orphans >= self.count:
            top = self.count

        self.set_current_page(number)

        api_page = number
        orders = self.get_orders(api_page)

        return self._get_page(orders, number, self)

    def page_range(self):
        """
        Returns a 1-based range of pages for iterating through within
        a template for loop.
        """
        page_count = self.num_pages

        pages = range(max(1, self.current_page-5), self.current_page)+range(self.current_page, min(page_count + 1, self.current_page+5))
        if 1 not in pages:
            pages = [1, None] + pages

        if page_count not in pages:
            pages = pages + [None, page_count]

        return pages

    def get_orders(self, page):
        if self.reverse_order:
            order = 'asc'
        else:
            order = 'desc'

        rep = requests.get(
            url = self.store.get_link('/admin/orders.json', api=True),
            params = {
                'limit': self.order_limit,
                'page': page,
                'status': self.status,
                'fulfillment_status': self.fulfillment,
                'financial_status': self.financial,
                'order': 'processed_at '+order
            }
        )

        return rep.json()['orders']