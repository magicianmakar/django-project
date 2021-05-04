import csv
import math
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO

from PIL import Image
from django import template
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Concat
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import escapejs
from django.utils.safestring import mark_safe
from django.views import View
from django.views.generic import TemplateView
from django.views.generic.list import ListView

import arrow
import bleach
import requests
import re
import simplejson as json
from barcode import generate
from pdfrw import PageMerge, PdfReader, PdfWriter
from pdfrw.pagemerge import RectXObj
from product_common import views as common_views
from product_common.lib import views as common_lib_views
from product_common.lib.views import PagingMixin, upload_image_to_aws, upload_object_to_aws
from product_common.models import ProductImage, ProductSupplier
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg

from shopified_core import permissions
from shopified_core.shipping_helper import get_counrties_list
from shopified_core.utils import (
    app_link,
    safe_int,
    safe_float,
    aws_s3_context as images_aws_s3_context,
)
from shopified_core.models_utils import get_store_model
from churnzero_core.utils import post_churnzero_product_import
from analytic_events.models import SupplementLabelForApprovalEvent
from supplements.lib.authorizenet import create_customer_profile, create_payment_profile
from supplements.lib.image import get_order_number_label, get_payment_pdf
from supplements.models import (
    AuthorizeNetCustomer,
    Payout,
    PLSOrder,
    PLSOrderLine,
    PLSupplement,
    ShippingGroup,
    UserSupplement,
    UserSupplementImage,
    UserSupplementLabel
)

from .forms import (
    AllLabelFilterForm,
    BillingForm,
    CommentForm,
    LabelFilterForm,
    LineFilterForm,
    MyOrderFilterForm,
    OrderFilterForm,
    PayoutFilterForm,
    PLSupplementEditForm,
    PLSupplementFilterForm,
    PLSupplementForm,
    RefundPaymentsForm,
    ReportsQueryForm,
    UploadJSONForm,
    UserSupplementFilterForm,
    UserSupplementForm
)
from .utils import aws_s3_context, create_rows, report, send_email_against_comment
from .utils.basket import BasketStoreObj

register = template.Library()


class Index(common_views.IndexView):
    model = PLSupplement

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_queryset(self):
        queryset = super().get_queryset()

        if self.request.GET.get('only_unique'):
            unique_supplement_ids = UserSupplement.objects.filter(
                user=self.request.user.models_user
            ).values_list('pl_supplement_id')
            queryset = queryset.filter(id__in=unique_supplement_ids)

        form = PLSupplementFilterForm(self.request.GET)
        if form.is_valid():
            title = form.cleaned_data['title']
            if title:
                queryset = queryset.filter(title__icontains=title)

            tags = form.cleaned_data['tags']
            if tags:
                queryset = queryset.filter(tags__iexact=tags)

            product_type = form.cleaned_data['product_type']
            if product_type:
                queryset = queryset.filter(category__iexact=product_type)

        if not self.request.user.can('pls_admin.use') \
                and not self.request.user.can('pls_staff.use'):
            return queryset.filter(is_active=True)
        return queryset

    def get_template(self):
        return 'supplements/index.html'

    def get_new_product_url(self):
        return reverse('pls:product')

    def get_breadcrumbs(self):
        return [{'title': 'Products', 'url': reverse('pls:index')}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['supplements'] = context['products']
        context['form'] = PLSupplementFilterForm(self.request.GET)

        can_add, total_allowed, user_count = permissions.can_add_supplement(self.request.user)
        context['limit_reached'] = not can_add
        context['total_allowed'] = total_allowed
        context['user_count'] = user_count

        return context


class Product(common_views.ProductAddView):
    form = PLSupplementForm
    namespace = 'pls'
    template_name = "supplements/product.html"

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Products Admin', 'url': reverse('pls:all_user_supplements')},
            {'title': 'Add New Product', 'url': reverse('pls:product')},
        ]

    def process_valid_form(self, form, pl_supplement=None):
        request = self.request
        user_id = request.user.id

        template = request.FILES.get('template', None)
        thumbnail = request.FILES.get('thumbnail', None)
        approved_label = request.FILES.get('approvedlabel', None)

        if template:
            template_url = upload_image_to_aws(template, 'supplement_label', user_id)
        else:
            template_url = pl_supplement.label_template_url

        if thumbnail:
            thumbnail_url = upload_image_to_aws(thumbnail, 'supplement_image', user_id)
        else:
            thumbnail_url = pl_supplement.images.get(position=0).image_url

        pl_supplement = form.save(commit=False)
        certificate = request.FILES.get('authenticity_certificate', None)
        if certificate:
            certificate_url = upload_image_to_aws(certificate, 'pls_certificate', user_id)
            pl_supplement.authenticity_certificate_url = certificate_url

        if approved_label:
            pl_supplement.approved_label_url = upload_image_to_aws(approved_label, 'pre_approved_label', user_id)

        pl_supplement.label_template_url = template_url
        pl_supplement.save()
        form.save_m2m()

        pl_supplement.images.all().delete()
        pl_supplement.images.create(
            product=pl_supplement,
            position=0,
            image_url=thumbnail_url,
        )


class ProductEdit(Product):
    form = PLSupplementEditForm
    supplement = None

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_supplement(self, supplement_id):
        return get_object_or_404(PLSupplement, id=supplement_id)

    def get_breadcrumbs(self, supplement_id):
        kwargs = {'supplement_id': supplement_id}
        return [
            {'title': 'Products Admin', 'url': reverse('pls:all_user_supplements')},
            {'title': 'Edit Product', 'url': reverse('pls:product_edit', kwargs=kwargs)},
        ]

    def get(self, request, supplement_id):
        self.supplement = self.get_supplement(supplement_id)
        form_data = self.supplement.to_dict()

        form_data['shipping_countries'] = self.supplement.shipping_countries.all()
        form_data['label_size'] = self.supplement.label_size
        form_data['weight'] = self.supplement.weight
        form_data['inventory'] = self.supplement.inventory
        form_data['mockup_type'] = self.supplement.mockup_type
        form_data['product_information'] = self.supplement.product_information

        context = {
            'breadcrumbs': self.get_breadcrumbs(supplement_id),
            'form': self.form(initial=form_data, instance=self.supplement),
        }
        context['supplement'] = self.supplement

        return render(request, self.get_template(), context)

    def post(self, request, supplement_id):
        self.supplement = self.get_supplement(supplement_id)
        form = self.form(request.POST, request.FILES, instance=self.supplement)
        if form.is_valid():
            self.process_valid_form(form, self.supplement)
            return redirect(self.get_redirect_url())

        context = {
            'breadcrumbs': self.get_breadcrumbs(supplement_id),
            'form': form,
        }
        return render(request, self.get_template(), context)


class SendToStoreMixin(common_lib_views.SendToStoreMixin):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_api_data(self, user_supplement):
        data = user_supplement.to_dict()

        kwargs = {'supplement_id': user_supplement.id}
        original_url = reverse('pls:user_supplement', kwargs=kwargs)
        data['original_url'] = self.request.build_absolute_uri(original_url)
        data['user_supplement_id'] = user_supplement.id
        data['supplier'] = user_supplement.pl_supplement.supplier.title

        api_data = {}
        if user_supplement.current_label.is_approved:
            api_data = self.serialize_api_data(data)

        return api_data

    def serialize_api_data(self, data):
        return json.dumps(dict(
            title=data['title'],
            description=data['description'],
            type=data['category'],
            vendor=data['supplier'],
            weight=0,  # TODO: Confirm
            weight_unit="lbs",  # TODO: Confirm
            tags=data['tags'],
            variants=[],
            images=data['image_urls'],
            price=data['price'],
            cost_price=data['cost_price'],
            compare_at_price=data['compare_at_price'],
            original_url=data['original_url'],
            user_supplement_id=data['user_supplement_id'],
            sku=data['shipstation_sku'],
            store=dict(
                name=data['supplier'],
                url='',
            ),
        ), use_decimal=True)


class LabelMixin:
    def save_label(self, user, url, user_supplement):
        user_name = user.get_full_name()
        new_label = user_supplement.labels.create(url=url)

        comment = (f"{user_name} uploaded label #{new_label.id}.")
        self.create_comment(new_label.comments, comment, send_email=False)

        user_supplement.current_label = new_label
        user_supplement.current_label.generate_sku()
        user_supplement.save()

    def create_comment(self, comments, text, new_status='', is_private=False, send_email=True):
        tags = bleach.sanitizer.ALLOWED_TAGS + [
            'span',
            'p',
        ]
        attributes = bleach.sanitizer.ALLOWED_ATTRIBUTES
        attributes.update({'span': ['class']})
        text = bleach.clean(text, tags=tags, attributes=attributes)
        comment = comments.create(user=self.request.user,
                                  text=text,
                                  new_status=new_status,
                                  is_private=is_private)
        # Do not notify about your own comments
        if comment.label.user_supplement.user == self.request.user:
            send_email = False
        if send_email and not is_private:
            send_email_against_comment(comment)
        return comment

    def add_barcode_to_label(self, label):
        data = BytesIO()
        generate('CODE128', label.sku, output=data)

        data.seek(0)
        drawing = svg2rlg(data)

        barcode_data = BytesIO()
        renderPDF.drawToFile(drawing, barcode_data)

        barcode_data.seek(0)
        barcode_pdf = PdfReader(barcode_data)
        barcode_pdf.pages[0].Rotate = 270
        barcode_pages = PageMerge() + barcode_pdf.pages
        barcode_page = barcode_pages[0]

        label_data = BytesIO(requests.get(label.url).content)
        base_label_pdf = PdfReader(label_data)

        page_merge = PageMerge(base_label_pdf.pages[0]).add(barcode_page)
        barcode_obj = page_merge[-1]
        page_height = RectXObj(page_merge.page).h
        width, height, x = 0.3, 0.6, 8
        if (page_height / 72) <= 1:  # Height is returned in pt. pt / 72 = 1 in
            width, height, x = 0.2, 0.4, 12
        barcode_obj.scale(width, height)
        barcode_obj.x = x
        barcode_obj.y = page_height * 0.05
        page_merge.render()

        label_pdf = BytesIO()
        PdfWriter().write(label_pdf, base_label_pdf)

        label_pdf.seek(0)

        label.url = upload_supplement_object_to_aws(
            label.user_supplement,
            label_pdf,
            'label.pdf',
        )


class Supplement(LabelMixin, LoginRequiredMixin, View, SendToStoreMixin):
    template_name = 'supplements/supplement.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        # Permission check for new supplements only
        if request.resolver_match.url_name == 'supplement':
            can_add, total_allowed, user_count = permissions.can_add_supplement(request.user)
            if not can_add:
                messages.error(request, f"Your plan allow up to {total_allowed} "
                               + f"products, currently you have {user_count} products.")
                return redirect('pls:index')
            else:
                total_allowed = total_allowed if total_allowed > -1 else 'unlimited'
                only_unique_filter = f"{reverse('supplements:index')}?only_unique=1"
                add_supplements_text = f'<br>You can still create {total_allowed} product ' \
                                       + f'variations, click <a href="{only_unique_filter}">here</a> to see which.'

            unique_permissions = permissions.can_use_unique_supplement(request.user, kwargs.get('supplement_id'))
            unique_can_add, unique_total_allowed, unique_user_count = unique_permissions
            if not unique_can_add:
                messages.error(request, f"Your plan allows customization of {unique_total_allowed} "
                               + f"products, currently you customized {unique_user_count} products."
                               + add_supplements_text)
                return redirect('pls:index')

        if request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self, supplement_id):
        url = reverse('pls:supplement',
                      kwargs={'supplement_id': supplement_id})
        breadcrumbs = [
            {'title': 'Products', 'url': reverse('pls:index')},
            {'title': 'Product', 'url': url},
        ]
        return breadcrumbs

    def copy_images(self, user_supplement):
        current_urls = set(
            user_supplement.images.values_list('image_url', flat=True)
        )

        pls_images = ProductImage.objects.filter(
            product_id=user_supplement.pl_supplement_id
        )

        UserSupplementImage.objects.bulk_create([
            UserSupplementImage(position=i.position,
                                image_url=i.image_url,
                                user_supplement=user_supplement)
            for i in pls_images if i.image_url not in current_urls
        ])

    def get_supplement(self, user, supplement_id):
        if not self.request.user.can('pls_admin.use') \
                and not self.request.user.can('pls_staff.use'):
            return get_object_or_404(PLSupplement, id=supplement_id, is_active=True)
        return get_object_or_404(PLSupplement, id=supplement_id)

    def get_weight(self, weight):
        if not weight:
            weight = "0 lb"
        else:
            weight_in_oz = round(float(weight - math.floor(weight)) * 16, 1)
            weight_in_oz = f"{weight_in_oz} oz" if int(weight_in_oz) else ""
            weight = f"{int(weight)} lb {weight_in_oz}" if int(weight) else weight_in_oz
        return weight

    def get_supplement_data(self, user, supplement_id):
        supplement = self.get_supplement(user, supplement_id)

        form_data = supplement.to_dict()
        form_data['action'] = 'save'
        form_data['shipping_countries'] = supplement.shipping_groups_string
        form_data['label_size'] = supplement.label_size
        form_data['mockup_type'] = supplement.mockup_type
        form_data['mockup_slug'] = supplement.mockup_type.slug
        form_data['weight'] = self.get_weight(supplement.weight)
        form_data['inventory'] = supplement.inventory
        form_data['msrp'] = supplement.msrp
        form_data['label_presets'] = json.dumps(supplement.mockup_type.get_label_presets())

        api_data = {}
        if supplement.is_approved:
            api_data = self.get_api_data(supplement)

        store_type_and_data = self.get_store_data(user)

        data = dict(
            supplement=supplement,
            form_data=form_data,
            image_urls=form_data.pop('image_urls'),
            label_template_url=form_data.pop('label_template_url'),
            approved_label_url=supplement.approved_label_url,
            is_approved=supplement.is_approved,
            is_awaiting_review=supplement.is_awaiting_review,
            api_data=api_data,
            store_data=store_type_and_data['store_data'],
            store_types=store_type_and_data['store_types'],
            product_information=supplement.product_information,
            authenticity_cert=supplement.authenticity_certificate_url,
            mockup_layers=supplement.mockup_type.get_layers(),
        )

        if 'label_url' in form_data:
            data['label_url'] = form_data.pop('label_url')

        return data

    def get_form(self):
        return UserSupplementForm(self.request.POST, self.request.FILES)

    def save_supplement(self, form):
        supplement = form.save(commit=False)
        supplement.pl_supplement_id = self.supplement_id
        supplement.user_id = self.request.user.models_user.id
        supplement.tags = form.cleaned_data['tags']
        supplement.seen_users = json.dumps(['All'])
        supplement.save()
        return supplement

    def save(self, request):
        user = request.user.models_user
        form = self.get_form()
        if form.is_valid():
            new_user_supplement = self.save_supplement(form)

            # Always use saved label URL for pre-approved labels
            upload_url = form.cleaned_data['upload_url']
            if form.cleaned_data['action'] == 'preapproved':
                upload_url = new_user_supplement.pl_supplement.approved_label_url
                self.save_label(user, upload_url, new_user_supplement)
            elif upload_url:
                self.save_label(user, upload_url, new_user_supplement)

            # Old images should be removed when new label is uploaded
            mockup_urls = request.POST.getlist('mockup_urls')
            if len(mockup_urls) or upload_url:
                new_user_supplement.images.all().delete()
                for position, mockup_url in enumerate(mockup_urls):
                    new_user_supplement.images.create(image_url=mockup_url, position=position)

            if not new_user_supplement.images.count():
                self.copy_images(new_user_supplement)

            is_draft_label = new_user_supplement.current_label is not None \
                and new_user_supplement.current_label.status == UserSupplementLabel.DRAFT

            if form.cleaned_data['action'] == 'preapproved':
                new_user_supplement.current_label.status = UserSupplementLabel.APPROVED
                self.add_barcode_to_label(new_user_supplement.current_label)
                new_user_supplement.current_label.save()

                label_class = 'label-primary'
                comment = (f"<strong>Dropified</strong> set the status to "
                           f"<span class='label {label_class}'>"
                           f"{new_user_supplement.current_label.status_string}</span>")
                comments = new_user_supplement.current_label.comments
                self.create_comment(comments, comment, new_status='approved')

                api_data = {}
                if new_user_supplement.is_approved:
                    api_data = self.get_api_data(new_user_supplement)
                return JsonResponse({'data': api_data, 'success': True})

            elif form.cleaned_data['action'] == 'approve' \
                    or upload_url and is_draft_label:  # Restart review process
                new_user_supplement.current_label.status = UserSupplementLabel.AWAITING_REVIEW
                new_user_supplement.current_label.save()
                SupplementLabelForApprovalEvent.objects.create(user=request.user,
                                                               product_name=new_user_supplement.title)

            kwargs = {'supplement_id': new_user_supplement.id}
            redirect_url = self.get_redirect_url(**kwargs)

            return redirect(f'{redirect_url}?unread=True')

        context = self.get_supplement_data(user, self.supplement_id)

        context['form'] = form
        context['breadcrumbs'] = self.get_breadcrumbs(self.supplement_id)

        return render(request, "supplements/supplement.html", context)

    def get_redirect_url(self, *args, **kwargs):
        return reverse("pls:user_supplement", kwargs=kwargs)

    def get(self, request, supplement_id):
        aws = aws_s3_context()
        aws_images = images_aws_s3_context()
        context = self.get_supplement_data(request.user, supplement_id)

        context.update({
            'breadcrumbs': self.get_breadcrumbs(supplement_id),
            'form': UserSupplementForm(initial=context['form_data']),
            'aws_available': aws['aws_available'],
            'aws_policy': aws['aws_policy'],
            'aws_signature': aws['aws_signature'],
            'aws_images': aws_images,
        })
        return render(request, self.template_name, context)

    def post(self, request, supplement_id):
        self.supplement_id = supplement_id
        return self.save(request)


class UserSupplementView(Supplement):
    template_name = 'supplements/user_supplement.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self, supplement_id):
        url = reverse('pls:user_supplement',
                      kwargs={'supplement_id': supplement_id})
        breadcrumbs = [
            {'title': 'Products', 'url': reverse('pls:index')},
            {'title': 'My Products', 'url': url},
        ]
        return breadcrumbs

    def get_label_context_data(self, *args, **kwargs):
        user_supplement = kwargs['label'].user_supplement
        aws = aws_s3_context()
        api_data = self.get_api_data(user_supplement)
        store_type_and_data = self.get_store_data(self.request.user)
        new_version_url = None
        current_label = user_supplement.current_label
        if current_label:
            new_version_url = reverse('pls:label_detail',
                                      kwargs={'label_id': current_label.id})
        all_comments = []
        for label in user_supplement.labels.all().order_by('-created_at'):
            comments = label.comments
            if self.request.user.can('pls_admin.use') or self.request.user.can('pls_staff.use'):
                comments = comments.all().order_by('-created_at')
            else:
                comments = comments.all().exclude(is_private=True).order_by('-created_at')
            if comments:
                all_comments.append(comments)

        unread = self.request.GET.get('unread', 'False')
        if unread != 'True':
            user_supplement.mark_as_read(self.request.user.id)

        return dict(
            label=kwargs['label'],
            api_data=api_data,
            store_data=store_type_and_data['store_data'],
            store_types=store_type_and_data['store_types'],
            new_version_url=new_version_url,
            aws_available=aws['aws_available'],
            aws_policy=aws['aws_policy'],
            aws_signature=aws['aws_signature'],
            all_comments=all_comments,
            aws_images=images_aws_s3_context(),
            mockup_layers=user_supplement.pl_supplement.mockup_type.get_layers(),
        )

    def get_supplement_data(self, user, supplement_id):
        supplement = self.get_supplement(user, supplement_id)

        form_data = supplement.to_dict()
        form_data['action'] = 'save'
        form_data['shipping_countries'] = supplement.shipping_groups_string
        form_data['label_size'] = supplement.pl_supplement.label_size
        form_data['mockup_type'] = supplement.pl_supplement.mockup_type
        form_data['mockup_slug'] = supplement.pl_supplement.mockup_type.slug
        form_data['weight'] = self.get_weight(supplement.pl_supplement.weight)
        form_data['inventory'] = supplement.pl_supplement.inventory
        form_data['label_presets'] = supplement.get_label_presets_json()

        api_data = {}
        if supplement.is_approved:
            api_data = self.get_api_data(supplement)

        store_type_and_data = self.get_store_data(user)
        is_submitted = False
        label_context = {}
        if supplement.current_label:
            is_submitted = supplement.current_label.status != UserSupplementLabel.DRAFT
            label_context = self.get_label_context_data(label=supplement.current_label)

        comment_form_data = dict(
            mockup_slug=supplement.pl_supplement.mockup_type.slug,
            label_presets=supplement.get_label_presets_json(),
            label_size=supplement.pl_supplement.label_size,
        )

        data = dict(
            supplement=supplement,
            form_data=form_data,
            image_urls=form_data.pop('image_urls'),
            label_template_url=form_data.pop('label_template_url'),
            is_approved=supplement.is_approved,
            is_awaiting_review=supplement.is_awaiting_review,
            api_data=api_data,
            store_data=store_type_and_data['store_data'],
            store_types=store_type_and_data['store_types'],
            product_information=supplement.pl_supplement.product_information,
            authenticity_cert=supplement.pl_supplement.authenticity_certificate_url,
            is_submitted=is_submitted,
            mockup_layers=supplement.pl_supplement.mockup_type.get_layers(),
            comment_form=CommentForm(initial=comment_form_data),
            user_buttons=True,
        )

        if 'label_url' in form_data:
            data['label_url'] = form_data.pop('label_url')

        data.update(label_context)

        return data

    def get_form(self):
        user_supplement = UserSupplement.objects.get(id=self.supplement_id)
        return UserSupplementForm(self.request.POST,
                                  instance=user_supplement)

    def get_supplement(self, user, supplement_id):
        return get_object_or_404(
            UserSupplement,
            user=user.models_user,
            id=supplement_id,
            is_deleted=False,
        )

    def save_supplement(self, form):
        return form.save()


class LabelHistory(UserSupplementView):
    template_name = 'supplements/label_history.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self, supplement_id):
        supplement = self.get_supplement(self.request.user, supplement_id)
        url = reverse('pls:user_supplement',
                      kwargs={'supplement_id': supplement.id})
        breadcrumbs = [
            {'title': 'Products', 'url': reverse('pls:index')},
            {'title': supplement.title, 'url': url},
            {'title': 'Label History', 'url': self.request.path},
        ]
        return breadcrumbs

    def get_redirect_url(self, supplement_id):
        kwargs = {'supplement_id': supplement_id}
        return reverse('pls:label_history', kwargs=kwargs)

    @transaction.atomic
    def post(self, request, supplement_id):
        user_supplement = self.get_supplement(request.user, supplement_id)
        label_id = user_supplement.current_label.id

        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            self.label = label = get_object_or_404(UserSupplementLabel, id=label_id)
        else:
            self.label = label = get_object_or_404(UserSupplementLabel, id=label_id, user_supplement__user=request.user.models_user)

        comments = label.comments

        reverse_url = self.get_redirect_url(user_supplement.id)

        action = request.POST['action']
        form = CommentForm()

        if action == 'comment':
            form = CommentForm(request.POST)
            if form.is_valid():
                comment = form.cleaned_data['comment']
                if comment:
                    is_private = form.cleaned_data['is_private']
                    self.create_comment(comments, comment, is_private=is_private)
                    user_supplement.mark_as_unread(request.user.id)
                    reverse_url = f'{reverse_url}?unread=True'

                # Restart review process for new labels
                upload_url = form.cleaned_data['upload_url']
                if upload_url:
                    user_supplement.label_presets = request.POST.get('label_presets') or '{}'
                    self.save_label(request.user, upload_url, user_supplement)
                    user_supplement.current_label.status = UserSupplementLabel.AWAITING_REVIEW
                    user_supplement.current_label.save()
                    SupplementLabelForApprovalEvent.objects.create(user=request.user,
                                                                   product_name=user_supplement.title)

                # Old images should be removed when new label is uploaded
                mockup_urls = request.POST.getlist('mockup_urls')
                if len(mockup_urls) or upload_url:
                    user_supplement.images.all().delete()
                    for position, mockup_url in enumerate(mockup_urls):
                        user_supplement.images.create(image_url=mockup_url, position=position)

                return redirect(reverse_url)

        context = self.get_supplement_data(request.user, user_supplement.id)
        context.update({
            'breadcrumbs': self.get_breadcrumbs(supplement_id),
            'comment_form': form,
        })

        return render(request, self.template_name, context)


class AdminLabelHistory(LabelHistory):
    template_name = 'supplements/label_history_admin.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_supplement(self, user, supplement_id):
        return get_object_or_404(UserSupplement, id=supplement_id)

    def get_redirect_url(self, supplement_id):
        kwargs = {'supplement_id': supplement_id}
        return reverse('pls:admin_label_history', kwargs=kwargs)

    @transaction.atomic
    def post(self, request, supplement_id):
        user_supplement = self.get_supplement(request.user, supplement_id)
        label = user_supplement.current_label
        action = request.POST.get('action')

        reverse_url = self.get_redirect_url(user_supplement.id)

        if action in (label.APPROVED, label.REJECTED):
            label.status = action
            label.save()

            label_class = 'label-danger'
            if action == label.APPROVED:
                label_class = 'label-primary'
                # If a label does not have SKU, needs to be generated for barcode
                if label.sku == '':
                    label.generate_sku()
                self.add_barcode_to_label(label)
                label.save()

            comment = (f"<strong>{request.user.get_full_name()}</strong> "
                       f"set the status to <span class='label {label_class}'>"
                       f"{label.status_string}</span>")
            self.create_comment(label.comments, comment, new_status=action)

            return redirect(reverse_url)

        # Call action to comment label for admins
        return super().post(request, supplement_id)


class MySupplements(LoginRequiredMixin, View):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def add_filters(self, queryset, form):
        status = form.cleaned_data['status']
        if status:
            queryset = queryset.filter(current_label__status=status)
        sku = form.cleaned_data['sku']
        if sku:
            queryset = queryset.filter(current_label__sku=sku)
        title = form.cleaned_data['title']
        if title:
            queryset = queryset.filter(title__icontains=title)
        return queryset

    def get(self, request):
        breadcrumbs = [
            {'title': 'Products', 'url': reverse('pls:index')},
            {'title': 'My Products', 'url': reverse('pls:my_supplements')},
        ]
        form = UserSupplementFilterForm(self.request.GET)
        queryset = request.user.models_user.pl_supplements.filter(pl_supplement__is_active=True)

        if form.is_valid():
            queryset = self.add_filters(queryset, form)

        temp_queryset = queryset
        queryset = queryset.exclude(is_deleted=True)
        len_supplement = len(queryset)
        if len_supplement == 1:
            len_supplement = "1 product."
        elif len_supplement > 0:
            len_supplement = f"{len_supplement} products."

        supplements = [i for i in queryset]

        context = {
            'breadcrumbs': breadcrumbs,
            'supplements': create_rows(supplements, 4),
            'form': UserSupplementFilterForm(self.request.GET),
            'count': len_supplement
        }

        deleted_sku = len(temp_queryset.filter(is_deleted=True))
        if deleted_sku and self.request.GET:
            context.update({
                'deleted_supplement_found': deleted_sku
            })
        return render(request, "supplements/userproduct.html", context)


class MyLabels(LoginRequiredMixin, PagingMixin):

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = self.add_filters(queryset)

        form = self.form = LabelFilterForm(self.request.GET)
        if form.is_valid():
            status = form.cleaned_data['status']
            if status:
                queryset = queryset.filter(current_label__status__in=status)

            sku = form.cleaned_data['sku']
            if sku:
                queryset = queryset.filter(labels__sku=sku)

            date = self.request.GET.get('date', None)
            updated_at_start, updated_at_end = None, None
            if date:
                try:
                    daterange_list = date.split('-')
                    tz = timezone.localtime(timezone.now()).strftime(' %z')
                    updated_at_start = arrow.get(daterange_list[0] + tz, r'MM/DD/YYYY Z').datetime
                    if len(daterange_list) > 1 and daterange_list[1]:
                        updated_at_end = arrow.get(daterange_list[1] + tz, r'MM/DD/YYYY Z')
                        updated_at_end = updated_at_end.span('day')[1].datetime
                except:
                    pass
                else:
                    if updated_at_start:
                        queryset = queryset.filter(current_label__updated_at__gte=updated_at_start)
                    if updated_at_end:
                        queryset = queryset.filter(current_label__updated_at__lte=updated_at_end)

        return queryset

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        self.add_paging_context(context)

        len_supplements = context['paginator'].count
        if len_supplements == 1:
            supplements_count = "1 user product"
        else:
            supplements_count = f"{len_supplements} user products."

        context.update({
            'breadcrumbs': self.get_breadcrumbs(),
            'supplements_count': supplements_count,
            'user_supplements': context['object_list'],
            'form': self.form,
            'date_range': self.request.GET.get('date', None),
        })
        return context


class AllUserSupplements(MyLabels, ListView):
    paginate_by = 20
    ordering = '-created_at'
    template_name = 'supplements/all_user_supplements.html'
    model = UserSupplement

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_ordering(self):
        order_by = self.request.GET.get('sort', 'newest')
        sort_map = {
            'newest': '-current_label__updated_at',
            'oldest': 'current_label__updated_at'
        }
        if order_by not in ['newest', 'oldest']:
            order_by = 'newest'
        return sort_map[order_by]

    def add_filters(self, queryset):
        return queryset.exclude(Q(current_label__isnull=True)
                                | Q(current_label__status=UserSupplementLabel.DRAFT)
                                | Q(current_label__user_supplement__is_deleted=True))

    def get_breadcrumbs(self):
        return [
            {'title': 'Products Admin', 'url': reverse('pls:all_user_supplements')},
            {'title': 'User Products', 'url': reverse('pls:all_user_supplements')},
        ]

    def get_queryset(self):
        queryset = super().get_queryset()

        form = AllLabelFilterForm(self.request.GET)
        if form.is_valid():
            label_user_name = form.cleaned_data['label_user_name']
            if label_user_name:
                queryset = queryset.annotate(
                    name=Concat('user__first_name', models.Value(' '), 'user__last_name')
                ).filter(
                    Q(user__email__icontains=label_user_name)
                    | Q(user_id=safe_int(label_user_name, None))
                    | Q(name__icontains=label_user_name)
                )

            product_sku = form.cleaned_data['product_sku']
            if product_sku:
                queryset = queryset.filter(pl_supplement__shipstation_sku__in=product_sku)

            title = form.cleaned_data['title']
            if title:
                queryset = queryset.filter(pl_supplement__title__icontains=title)

            comments_status = form.cleaned_data['comments_status']
            if comments_status:
                user_id = self.request.user.id
                seen_ids = []
                for entry in queryset:
                    seen_users = entry.get_seen_users_list()
                    if 'All' in seen_users or user_id in seen_users:
                        seen_ids.append(entry.id)

                if comments_status == 'read':
                    queryset = queryset.filter(id__in=seen_ids)
                elif comments_status == 'unread':
                    queryset = queryset.exclude(id__in=seen_ids)

            supplier = form.cleaned_data['supplier']
            if supplier:
                queryset = queryset.filter(pl_supplement__supplier_id=supplier)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['all_label_form'] = AllLabelFilterForm(self.request.GET)
        return context


def upload_supplement_object_to_aws(user_supplement, obj, name):
    # Randomize filename in order to not overwrite an existing file
    path = f'uploads/u{user_supplement.user.id}/pls_label/{user_supplement.id}'
    return upload_object_to_aws(path, name, obj)


class Label(LabelMixin, LoginRequiredMixin, View, SendToStoreMixin):

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        user_supplement = self.label.user_supplement
        user_supplement_url = reverse(
            'pls:user_supplement',
            kwargs={'supplement_id': user_supplement.id}
        )

        return [
            {'title': 'Products', 'url': reverse('pls:index')},
            {'title': user_supplement.title, 'url': user_supplement_url},
            {'title': 'Label', 'url': self.request.path},
        ]

    def get_context_data(self, **kwargs):
        user_supplement = kwargs['label'].user_supplement
        aws = aws_s3_context()
        api_data = self.get_api_data(user_supplement)
        store_type_and_data = self.get_store_data(self.request.user)
        new_version_url = None
        current_label = user_supplement.current_label
        if current_label:
            new_version_url = reverse('pls:label_detail',
                                      kwargs={'label_id': current_label.id})

        return dict(
            label=kwargs['label'],
            api_data=api_data,
            store_data=store_type_and_data['store_data'],
            store_types=store_type_and_data['store_types'],
            new_version_url=new_version_url,
            aws_available=aws['aws_available'],
            aws_policy=aws['aws_policy'],
            aws_signature=aws['aws_signature'],
            aws_images=images_aws_s3_context(),
            mockup_layers=user_supplement.pl_supplement.mockup_type.get_layers(),
        )

    def get(self, request, label_id):
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            self.label = label = get_object_or_404(UserSupplementLabel, id=label_id)
        else:
            self.label = label = get_object_or_404(UserSupplementLabel, id=label_id, user_supplement__user=request.user.models_user)

        comments = label.comments

        form_data = dict(
            mockup_slug=label.user_supplement.pl_supplement.mockup_type.slug,
            label_presets=label.user_supplement.get_label_presets_json(),
        )

        context = self.get_context_data(label=label)
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            comments = comments.all().order_by('-created_at')
        else:
            comments = comments.all().exclude(is_private=True).order_by('-created_at')

        context.update({
            'form': CommentForm(initial=form_data),
            'comments': comments,
        })

        return render(request, "supplements/label_detail.html", context)


class OrdersShippedWebHook(common_views.OrdersShippedWebHookView):
    order_model = PLSOrder
    order_line_model = PLSOrderLine


class Order(common_views.OrderView):
    model = PLSOrder
    paginate_by = 20
    ordering = '-created_at'
    filter_form = OrderFilterForm
    namespace = 'pls'
    refund_form = RefundPaymentsForm
    template_name = 'supplements/plsorder_list.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Products Admin', 'url': reverse('pls:all_user_supplements')},
            {'title': 'Payments', 'url': reverse('pls:order_list')},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'form': self.form,
            'refund_form': self.refund_form,
            'breadcrumbs': self.get_breadcrumbs(),
            'date_range': self.request.GET.get('date', None),
        })
        self.add_paging_context(context)
        return context

    def void_transaction(self, request, refund, transaction_id):
        transaction_id, errors = request.user.authorize_net_customer.void(transaction_id)
        if transaction_id:
            refund.transaction_id = transaction_id
            refund.status = 'voided'
            refund.save()
            messages.success(request, f"The transaction with the id {transaction_id} is voided.")
        elif errors:
            messages.error(request, f"{errors[0]}.")

    def retrieve_transaction_status(self, request, transaction_id):
        transaction_status = request.user.authorize_net_customer.status(transaction_id)
        return transaction_status

    def post(self, request):
        refund_form = self.refund_form = self.refund_form(request.POST)
        if refund_form.is_valid():
            with transaction.atomic():
                refund = refund_form.save()
                order_id = request.POST.get('order_id', '')
                items_data = request.POST.get('line_items_data', '')

                if order_id:
                    order = get_object_or_404(PLSOrder, id=order_id)
                    order.refund = refund
                    order.save()

                    if items_data:
                        for id, amount in json.loads(items_data).items():
                            line = order.order_items.get(id=id)
                            line.refund_amount = amount
                            line.save()

                    transaction_id = None
                    if order.stripe_transaction_id:
                        transaction_id, errors = request.user.authorize_net_customer.refund(
                            refund.amount - refund.fee + refund.shipping,
                            order.stripe_transaction_id,
                        )

                    if transaction_id:
                        refund.transaction_id = transaction_id
                        refund.save()
                        messages.success(request, f"The transaction with the id {order.stripe_transaction_id} is refunded.")
                    elif errors:
                        error_code = ''
                        reg = re.search(r'^[a-zA-Z0-9]+[:]', errors[0])
                        if reg is not None:
                            error_code = reg[0]
                        # Void a transaction if error code is 54 which means transaction cannot be refunded
                        if error_code == '54:':
                            transaction_status = self.retrieve_transaction_status(request, order.stripe_transaction_id)
                            # Ensure to void only Unsettled transaction
                            if transaction_status == 'capturedPendingSettlement':
                                self.void_transaction(request, refund, order.stripe_transaction_id)
                            else:
                                messages.error(request, f"The transaction with the id {order.stripe_transaction_id} cannot be refunded or voided.")
                                transaction.set_rollback(True)
                        else:
                            messages.error(request, f"{errors[0]}.")
                            transaction.set_rollback(True)

        self.object_list = self.get_queryset()
        context = self.get_context_data()

        return render(request, self.template_name, context=context)


class OrderDetailMixin(LoginRequiredMixin, View):
    def get_breadcrumbs(self, order):
        return [
            {'title': 'Products', 'url': reverse('pls:index')},
            {'title': 'My Payments', 'url': reverse('pls:my_orders')},
            {'title': order.order_number, 'url': reverse('pls:order_detail', kwargs={'order_id': order.id})}
        ]

    def get_context_data(self, **kwargs):
        order = kwargs['order']

        line_items = order.order_items.all()
        for line_item in line_items:
            line_item.supplement = line_item.label.user_supplement.to_dict()
            line_item.line_total = "${:.2f}".format((line_item.amount * line_item.quantity) / 100.)

        store = get_store_model(order.store_type).objects.get(id=order.store_id)

        if not self.request.user.can('pls_admin.use') and not self.request.user.can('pls_staff.use'):
            # Make sure this user have access to this order store
            if isinstance(store, BasketStoreObj):
                permissions.user_can_view(self.request.user, self.order)
            else:
                permissions.user_can_view(self.request.user, store)

        shipping_address = store.get_order(order.store_order_id).get('shipping_address')

        return dict(
            order=order,
            shipping_address=shipping_address,
            breadcrumbs=self.get_breadcrumbs(order),
            line_items=line_items
        )

    def get(self, request, order_id):
        self.order = order = get_object_or_404(PLSOrder, id=order_id)
        context = self.get_context_data(order=order)

        return render(request, "supplements/order_detail.html", context)


class OrderDetail(OrderDetailMixin):

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()


class MyOrderDetail(OrderDetailMixin):

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()


class MyOrders(common_views.OrderView):
    template_name = 'supplements/user_order_list.html'
    model = PLSOrder
    filter_form = OrderFilterForm
    namespace = 'pls'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Products', 'url': reverse('pls:index')},
            {'title': 'My Payments', 'url': reverse('pls:my_orders')},
        ]

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(user=self.request.user.models_user)

        form = self.form = MyOrderFilterForm(self.request.GET)
        if form.is_valid():
            order_number = form.cleaned_data['order_number']
            if order_number:
                queryset = queryset.filter(order_number=order_number)

            transaction_id = form.cleaned_data['transaction_id']
            if transaction_id:
                queryset = queryset.filter(
                    Q(stripe_transaction_id=transaction_id)
                    | Q(id=transaction_id)
                )

            date = self.request.GET.get('date', None)
            created_at_start, created_at_end = None, None
            if date:
                try:
                    daterange_list = date.split('-')
                    tz = timezone.localtime(timezone.now()).strftime(' %z')
                    created_at_start = arrow.get(daterange_list[0] + tz, r'MM/DD/YYYY Z').datetime
                    if len(daterange_list) > 1 and daterange_list[1]:
                        created_at_end = arrow.get(daterange_list[1] + tz, r'MM/DD/YYYY Z')
                        created_at_end = created_at_end.span('day')[1].datetime
                except:
                    pass
                else:
                    if created_at_start:
                        queryset = queryset.filter(created_at__gte=created_at_start)
                    if created_at_end:
                        queryset = queryset.filter(created_at__lte=created_at_end)

        return queryset

    def get(self, *args, **kwargs):
        csv_export = bool(self.request.GET.get('export'))
        # Always export current page to CSV using hidden input
        self.page_kwarg = 'csv_page' if csv_export else self.page_kwarg

        # Get list results the normal way
        result = super().get(*args, **kwargs)
        if not csv_export:
            return result

        response = HttpResponse(content_type='text/csv')
        filename = f"payments-page{self.request.GET.get('csv_page') or 1}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow([
            'Order #',
            'Shipping Cost',
            'Supplement',
            'Supplement URL',
            'Quantity',
            'Cost (USD)',
        ])

        for pls_order in result.context_data['object_list']:
            order_row_prefix = [
                pls_order.order_number,
                Decimal(pls_order.shipping_price) / 100
            ]

            order_items = pls_order.order_items.all()
            multiple_order_items = len(order_items) > 1
            if multiple_order_items:
                writer.writerow(order_row_prefix + ['[Multiple]'])
                item_row_prefix = ['', '']
            else:
                # Write all in one row for orders with one item
                item_row_prefix = order_row_prefix

            for pls_item in order_items:
                user_supplement = pls_item.label.user_supplement
                supplement_link = app_link(reverse('pls:user_supplement', kwargs={
                    'supplement_id': user_supplement.id
                }))

                writer.writerow(item_row_prefix + [
                    f'=HYPERLINK("{supplement_link}", "{user_supplement.title}")',
                    supplement_link,
                    pls_item.quantity,
                    Decimal(pls_item.amount) / 100 * pls_item.quantity,
                ])

        return response


class PayoutView(common_views.PayoutView):
    model = Payout
    paginate_by = 20
    ordering = '-created_at'
    filter_form = PayoutFilterForm
    namespace = 'pls'
    order_line_class = PLSOrderLine
    template_name = 'supplements/payout_list.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Products Admin', 'url': reverse('pls:all_user_supplements')},
            {'title': 'Payouts', 'url': reverse('pls:payout_list')},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['supplier_list'] = [dict(
            id=s.id,
            title=s.title
        ) for s in ProductSupplier.get_suppliers()]

        return context

    def get(self, *args, **kwargs):
        csv_export = bool(self.request.GET.get('export'))
        ref_id = self.request.GET.get('ref_id')
        if ref_id:
            ref_id = int(ref_id)

        # Get list results the normal way
        result = super().get(*args, **kwargs)

        # Absence of these params means that payout list is requested
        if not csv_export or not ref_id:
            return result

        response = HttpResponse(content_type='text/csv')
        filename = f"payout-{self.request.GET.get('ref_num') or ref_id}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow([
            'Payout #',
            'Order #',
            'DB SKU',
            'Label SKU',
            'Quantity',
            'Wholesale Cost',
            'Shipping Revenue',
        ])

        payout = self.model.objects.get(id=ref_id)
        if payout.supplier.is_shipping_supplier:
            order_lines = self.order_line_class.objects.filter(shipping_payout_id=ref_id)
        else:
            order_lines = self.order_line_class.objects.filter(line_payout_id=ref_id)

        if order_lines.count():
            for order_line in order_lines:
                payout_num = order_line.line_payout
                order_num = order_line.pls_order.order_number
                shipping_revenue = order_line.pls_order.shipping_price_string
                user_supplement = order_line.label.user_supplement
                db_sku = user_supplement.pl_supplement.shipstation_sku
                label_sku = order_line.label.sku
                quantity = order_line.quantity
                wholesale_cost = user_supplement.pl_supplement.wholesale_price
                wholesale_cost = "${:.2f}".format(wholesale_cost)

                data = [
                    payout_num,
                    order_num,
                    db_sku,
                    label_sku,
                    quantity,
                    wholesale_cost,
                    shipping_revenue
                ]
                writer.writerow(data)
        else:
            data = [
                'N/A',
                'N/A',
                'N/A',
                'N/A',
                'N/A',
                'N/A',
                'N/A'
            ]
            writer.writerow(data)
        return response


class PayoutDetail(LoginRequiredMixin, TemplateView):
    template_name = 'supplements/payout_detail.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Products Admin', 'url': reverse('pls:all_user_supplements')},
            {'title': 'Payouts', 'url': reverse('pls:payout_list')},
            self.payout.reference_number,
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.payout = get_object_or_404(Payout, id=kwargs['payout_id'])

        context.update({
            'breadcrumbs': self.get_breadcrumbs(),
            'payout': self.payout,
        })

        return context


class OrderItemListView(common_views.OrderItemListView):
    model = PLSOrderLine
    ordering = '-created_at'
    filter_form = LineFilterForm
    namespace = 'pls'
    cancelled_orders_cache = {}
    template_name = 'supplements/plsorderline_list.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Products Admin', 'url': reverse('pls:all_user_supplements')},
            {'title': 'Order Items', 'url': '%s?cancelled=on' % reverse('pls:orderitem_list')},
        ]


class GenerateLabel(LoginRequiredMixin, View):
    def add_clean_barcode_to_label(self, label):
        data = BytesIO()
        generate('CODE128', label.sku, output=data)

        data.seek(0)
        drawing = svg2rlg(data)

        barcode_data = BytesIO()

        image = Image.new('RGB', (100, 300), (255, 255, 255))
        blank_image_data = BytesIO()
        image.save(blank_image_data, format='pdf')

        blank_image_data.seek(0)
        blank_image_pdf = PdfReader(blank_image_data)
        blank_pages = PageMerge() + blank_image_pdf.pages
        blank_page = blank_pages[0]

        renderPDF.drawToFile(drawing, barcode_data)
        barcode_data.seek(0)
        barcode_pdf = PdfReader(barcode_data)
        barcode_pdf.pages[0].Rotate = 270
        barcode_pages = PageMerge() + barcode_pdf.pages
        barcode_page = barcode_pages[0]

        label_data = BytesIO(requests.get(label.url).content)
        base_label_pdf = PdfReader(label_data)

        page_merge = PageMerge(base_label_pdf.pages[0]).add(blank_page).add(barcode_page)
        barcode_obj = page_merge[-1]
        page_height = RectXObj(page_merge.page).h
        width, height, x = 0.2, 0.5, 8
        if (page_height / 72) <= 1:  # Height is returned in pt. pt / 72 = 1 in
            width, height, x = 0.2, 0.4, 12

        page_merge[1].scale(width, height)  # Blank space on top of old barcode
        page_merge[1].x = x
        page_merge[1].y = page_height * 0.05

        barcode_obj.scale(width, height)
        barcode_obj.x = x
        barcode_obj.y = page_height * 0.05
        page_merge.render()

        label_pdf = BytesIO()
        PdfWriter().write(label_pdf, base_label_pdf)

        label_pdf.seek(0)

        return upload_supplement_object_to_aws(
            label.user_supplement,
            label_pdf,
            'label.pdf',
        )

    def get_label(self, line_item):
        if self.request.GET.get('use_latest', False):
            label = line_item.label.user_supplement.labels.order_by('-created_at').first()
        else:
            label = line_item.label
        return label

    def get(self, request, line_id):
        use_latest = request.GET.get('use_latest', False)
        line_item = get_object_or_404(PLSOrderLine, id=line_id)

        if request.GET.get('validate'):
            new_pdf_label = self.add_clean_barcode_to_label(self.get_label(line_item))
            return JsonResponse({'url': new_pdf_label})

        elif request.GET.get('renew'):
            label = self.get_label(line_item)
            label.url = request.GET.get('renew')
            label.save()

        line_item.mark_printed()
        base_label_pdf = get_order_number_label(line_item, use_latest)
        output = BytesIO()
        PdfWriter().write(output, base_label_pdf)

        output.seek(0)
        return HttpResponse(output.read(), content_type='application/pdf')


class GeneratePaymentPDF(LoginRequiredMixin, View):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get(self, request, order_id):
        pls_order = get_object_or_404(PLSOrder, id=order_id)
        if not pls_order.stripe_transaction_id:
            return HttpResponse(status=404)

        pdf = get_payment_pdf(pls_order)

        file_name = f'{pls_order.order_number}-{pls_order.stripe_transaction_id}'
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{file_name}.pdf"'
        response.write(pdf)

        return response


class Billing(LoginRequiredMixin, TemplateView):
    template_name = 'supplements/billing.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if user.can('pls.use') and not user.is_subuser:
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Products', 'url': reverse('pls:index')},
            'Billing',
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            self.request.user.authorize_net_customer.retrieve()
        except AuthorizeNetCustomer.DoesNotExist:
            pass

        context.update({
            'breadcrumbs': self.get_breadcrumbs(),
            'countries': get_counrties_list(),
        })

        return context

    def post(self, request):
        error = ''
        form = self.form = self.get_form()
        if form.is_valid():
            user = self.request.user

            try:
                customer_id = user.authorize_net_customer.customer_id
            except AuthorizeNetCustomer.DoesNotExist:
                customer_id = None

            if not customer_id:
                customer_id = create_customer_profile(request.user)

            data = self.get_payment_data()
            payment_id, error = create_payment_profile(data, customer_id)
            if payment_id:
                self.add_ids_to_user(customer_id, payment_id)
                url = reverse('pls:billing')
                return redirect(url)

        context = self.get_context_data(form=form, error=error)
        return render(request, self.template_name, context=context)

    def add_ids_to_user(self, profile_id, payment_id):
        try:
            auth_net_user = self.request.user.authorize_net_customer
        except AuthorizeNetCustomer.DoesNotExist:
            auth_net_user = AuthorizeNetCustomer(
                user=self.request.user,
            )

        auth_net_user.customer_id = profile_id
        auth_net_user.payment_id = payment_id
        auth_net_user.save()

    def get_form(self):
        get_post = self.request.POST.get

        data = dict(
            name=get_post('cc-name'),
            cc_number=get_post('cc-number'),
            cc_expiry=get_post('cc-exp'),
            cc_cvv=get_post('cc-cvc'),
        )
        data.update(self.request.POST.dict())
        return BillingForm(data)

    def get_payment_data(self):
        data = self.form.cleaned_data
        month, year = data['cc_expiry'].split('/')
        month = month.strip()
        year = year.strip()
        data['cc_expiry'] = f'{year}-{month}'
        return data


class RemoveCreditCard(LoginRequiredMixin, View):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def post(self, request):
        try:
            self.request.user.authorize_net_customer.payment_id = None
            self.request.user.authorize_net_customer.save()
        except AuthorizeNetCustomer.DoesNotExist:
            pass

        return redirect(reverse('pls:billing'))


class UploadJSON(LoginRequiredMixin, TemplateView):
    template_name = 'supplements/upload_json.html'
    form = UploadJSONForm

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if settings.DEBUG and request.user.can('pls_admin.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Products Admin', 'url': reverse('pls:all_user_supplements')},
            {'title': 'Import / Export', 'url': reverse('pls:upload_json')},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update({
            'breadcrumbs': self.get_breadcrumbs(),
            'form': self.form,
        })
        return context

    def post(self, request):
        form = self.form = self.form(request.POST, request.FILES)

        if form.is_valid():
            upload = request.FILES['upload']
            data = json.loads(upload.read())

            for entry in data:
                pl_supplement = PLSupplement.objects.create(
                    title=entry['title'],
                    description=entry['description'],
                    category=entry['category'],
                    tags=entry['tags'],
                    cost_price=entry['cost_price'],
                    shipstation_sku=entry['shipstation_sku'],
                    label_template_url=entry['label_template_url'],
                    wholesale_price=entry['wholesale_price']
                )
                for url in entry['image_urls']:
                    pl_supplement.images.create(
                        product=pl_supplement,
                        position=0,
                        image_url=url,
                    )
                for country in entry['shipping_countries']:
                    group, _ = ShippingGroup.objects.get_or_create(
                        slug=country['slug'],
                        name=country['name'],
                        locations=country['locations'],
                        immutable=country['immutable'],
                    )
                    pl_supplement.shipping_countries.add(group)

                if request.user.models_user.profile.has_churnzero_account:
                    post_churnzero_product_import(request.user, entry['title'], 'Supplement Import')

            return redirect(reverse('pls:index'))
        return self.get(request)


class DownloadJSON(LoginRequiredMixin, View):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if settings.DEBUG and request.user.can('pls_admin.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get(self, request):
        data_list = []
        for supplement in PLSupplement.objects.all():
            data_list.append(supplement.to_dict())

        data = json.dumps(data_list, indent=2)
        response = HttpResponse(data, content_type='application/json')
        response['Content-Disposition'] = 'attachment; filename="supplements.json"'
        return response


class Autocomplete(View):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get(self, request, target):
        q = request.GET.get('query', request.GET.get('term', '')).strip()
        if not q:
            return JsonResponse({'query': q, 'suggestions': []}, safe=False)

        if target == 'users':
            results = []
            queryset = User.objects.annotate(
                count=models.Count('pl_supplements__labels'),
                full_name=models.functions.Concat('first_name', models.Value(' '), 'last_name')
            ).filter(count__gt=0)
            queryset = queryset.filter(models.Q(email__icontains=q) | models.Q(full_name__icontains=q))

            for result in queryset[:10]:
                results.append({
                    'value': result.full_name,
                    'data': result.id
                })

            return JsonResponse({'query': q, 'suggestions': results}, safe=False)

        else:
            return JsonResponse({'error': 'Unknown target'})


class Reports(LoginRequiredMixin, TemplateView):
    template_name = 'supplements/reports.html'
    form = ReportsQueryForm

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Products Admin', 'url': reverse('pls:all_user_supplements')},
            {'title': 'Reports', 'url': reverse('pls:reports')},
        ]

    def check_day_interval(self, obj, check):
        if obj.created_at.year == check.year and \
           obj.created_at.month == check.month and \
           obj.created_at.day == check.day:
            return obj

    def check_range_interval(self, obj, start, end):
        # change date object to datetime aware object for comparison
        if not start.tzinfo:
            start = timezone.make_aware(start, timezone.get_current_timezone())
        if not end.tzinfo:
            end = timezone.make_aware(end, timezone.get_current_timezone())

        if obj.created_at > start and obj.created_at < end:
            return obj

    def get_charts_data(self, all_orders, interval, start_at, end_at):
        data = None
        ds_l = None

        check_s = start_at
        check_e = end_at

        if interval == 'day':
            order_count_data = []
            order_cost_data = []
            pls_sale_data = []
            gross_profit_data = []
            label_data = []
            ds_l = '{} to {}'.format(check_s.strftime('%Y-%m-%d'), end_at.strftime('%Y-%m-%d'))
            while check_s <= check_e:
                filtered_orders = list(
                    filter(
                        lambda order: self.check_day_interval(order, check_s),
                        list(all_orders)
                    )
                )
                day_order_count = len(filtered_orders)
                day_order_cost = sum(order.amount for order in filtered_orders)
                order_items = []
                for order in filtered_orders:
                    order_items += list(order.order_items.all())
                day_pls_sale = sum(item.quantity for item in order_items)
                order_count_data.append(day_order_count)
                order_cost_data.append(
                    day_order_cost / 100.0 if day_order_cost else 0
                )
                pls_sale_data.append(
                    day_pls_sale if day_pls_sale else 0
                )
                gross_profit_data.append(
                    sum(((order.amount - order.wholesale_price) / 100.) for order in filtered_orders)
                )
                label_data.append(
                    '{}-{}-{}'.format(check_s.year, check_s.month, check_s.day)
                )
                check_s = check_s + timedelta(days=1)
            data = {
                'order_count_data': {
                    'data': order_count_data,
                    'label_data': label_data,
                    'dataset_label': ds_l
                },
                'order_cost_data': {
                    'data': order_cost_data,
                    'label_data': label_data,
                    'dataset_label': ds_l
                },
                'pls_sale_data': {
                    'data': pls_sale_data,
                    'label_data': label_data,
                    'dataset_label': ds_l
                },
                'gross_profit_data': {
                    'data': gross_profit_data,
                    'label_data': label_data,
                    'dataset_label': ds_l
                }
            }
        elif interval == 'month':
            order_count_data = []
            order_cost_data = []
            pls_sale_data = []
            gross_profit_data = []
            label_data = []
            ds_l = 'Year {}'.format(check_s.strftime('%Y'))
            while check_s <= check_e:
                days_in_m = report.get_days_in_month(check_s) - 1
                next_start = check_s + timedelta(days=days_in_m)
                if (check_e - check_s).days < days_in_m:
                    next_start = check_s + timedelta(days=(check_e - check_s).days + 1)
                filtered_orders = list(
                    filter(
                        lambda order: self.check_range_interval(order, check_s, check_e),
                        list(all_orders)
                    )
                )
                day_order_count = len(filtered_orders)
                day_order_cost = sum(order.amount for order in filtered_orders)
                order_items = []
                for order in filtered_orders:
                    order_items += list(order.order_items.all())
                day_pls_sale = sum(item.quantity for item in order_items)
                order_count_data.append(day_order_count)
                order_cost_data.append(
                    day_order_cost / 100.0 if day_order_cost else 0
                )
                pls_sale_data.append(
                    day_pls_sale if day_pls_sale else 0
                )
                gross_profit_data.append(
                    sum(((order.amount - order.wholesale_price) / 100.) for order in filtered_orders)
                )
                label_data.append(next_start.strftime('%B'))
                check_s = next_start + timedelta(days=1)
            data = {
                'order_count_data': {
                    'data': order_count_data,
                    'label_data': label_data,
                    'dataset_label': ds_l
                },
                'order_cost_data': {
                    'data': order_cost_data,
                    'label_data': label_data,
                    'dataset_label': ds_l
                },
                'pls_sale_data': {
                    'data': pls_sale_data,
                    'label_data': label_data,
                    'dataset_label': ds_l
                },
                'gross_profit_data': {
                    'data': gross_profit_data,
                    'label_data': label_data,
                    'dataset_label': ds_l
                }
            }
        else:
            order_count_data = []
            order_cost_data = []
            pls_sale_data = []
            gross_profit_data = []
            label_data = []
            ds_l = '{} to {}'.format(check_s.strftime('%Y-%m-%d'), check_e.strftime('%Y-%m-%d'))
            count = 1
            while check_s <= check_e:
                if check_s.weekday() > 0:
                    next_start = check_s + timedelta(days=(6 - check_s.weekday()))
                else:
                    next_start = check_s + timedelta(days=6)
                    if (check_e - check_s).days < 6:
                        next_start = check_s + timedelta(days=(check_e - check_s).days + 1)
                filtered_orders = list(
                    filter(
                        lambda order: self.check_range_interval(order, check_s, next_start),
                        list(all_orders)
                    )
                )
                day_order_count = len(filtered_orders)
                day_order_cost = sum(order.amount for order in filtered_orders)
                order_items = []
                for order in filtered_orders:
                    order_items += list(order.order_items.all())
                day_pls_sale = sum(item.quantity for item in order_items)
                order_count_data.append(day_order_count)
                order_cost_data.append(
                    day_order_cost / 100.0 if day_order_cost else 0
                )
                pls_sale_data.append(
                    day_pls_sale if day_pls_sale else 0
                )
                gross_profit_data.append(
                    sum(((order.amount - order.wholesale_price) / 100.) for order in filtered_orders)
                )
                label_data.append('Week {}'.format(count))
                check_s = next_start + timedelta(days=1)
                if count == 4:
                    count = 1
                else:
                    count += 1
            data = {
                'order_count_data': {
                    'data': order_count_data,
                    'label_data': label_data,
                    'dataset_label': ds_l
                },
                'order_cost_data': {
                    'data': order_cost_data,
                    'label_data': label_data,
                    'dataset_label': ds_l
                },
                'pls_sale_data': {
                    'data': pls_sale_data,
                    'label_data': label_data,
                    'dataset_label': ds_l
                },
                'gross_profit_data': {
                    'data': gross_profit_data,
                    'label_data': label_data,
                    'dataset_label': ds_l
                }
            }

        check_s = start_at
        check_e = end_at
        avg_order_count_data = []
        avg_order_label = []
        count = 1
        while check_s <= check_e:
            if check_s.weekday() > 0:
                next_start = check_s + timedelta(days=(6 - check_s.weekday()))
            else:
                next_start = check_s + timedelta(days=6)
            if (check_e - check_s).days < 6:
                next_start = check_s + timedelta(days=(check_e - check_s).days)
            filtered_orders = list(
                filter(
                    lambda order: self.check_range_interval(order, check_s, next_start),
                    list(all_orders)
                )
            )
            day_order_count = len(filtered_orders)
            num_days = (next_start - check_s).days + 1
            avg_order_count_data.append(round(day_order_count / num_days, 2))
            avg_order_label.append('Week {}'.format(count))
            check_s = next_start + timedelta(days=1)
            if count == 4:
                count = 1
            else:
                count += 1
        data['avg_order_data'] = {
            'data': avg_order_count_data,
            'label_data': avg_order_label,
            'dataset_label': ds_l
        }

        filtered_orders = list(
            filter(
                lambda order: self.check_range_interval(order, start_at, end_at),
                list(all_orders)
            )
        )

        all_sku = []
        sku_data = []
        all_title = []
        all_link = []
        for order in filtered_orders:
            for line_item in order.order_items.all():
                sku = line_item.label.user_supplement.pl_supplement.shipstation_sku
                title = line_item.label.user_supplement.pl_supplement.title
                pl_link = reverse('pls:supplement', kwargs={'supplement_id': line_item.label.user_supplement.id})
                if sku not in all_sku:
                    all_sku.append(sku)
                    sku_data.append(line_item.quantity)
                    all_title.append(title)
                    all_link.append(pl_link)
                else:
                    sku_data[all_sku.index(sku)] = sku_data[all_sku.index(sku)] + line_item.quantity
        if sku_data:
            all_sku, sku_data, all_title, all_link = report.sort_sku_data(
                all_sku,
                sku_data,
                all_title,
                all_link
            )
        data['pls_sku_data'] = {
            'data': sku_data,
            'label_data': all_sku,
            'dataset_label': ds_l,
            'title_data': all_title,
            'link_data': all_link
        }

        total_amount = sum(order.amount for order in filtered_orders)
        total_cost = sum(order.wholesale_price for order in filtered_orders)
        total_shipping_cost = sum(order.shipping_price for order in filtered_orders)
        gross_profit = (total_amount - (total_cost + total_shipping_cost)) / 100.
        total_revenue = total_amount / 100.
        total_orders = len(filtered_orders)
        all_items = []
        for order in filtered_orders:
            all_items += list(order.order_items.all())
        total_items = sum(item.quantity for item in all_items)
        total_sale = sum(order.sale_price for order in filtered_orders) / 100.
        total_profit = sum((order.sale_price - order.amount) for order in filtered_orders) / 100.

        data['gross_profit'] = report.millify(gross_profit)
        data['revenue'] = report.millify(total_revenue)
        data['total_orders'] = report.millify(total_orders)
        data['total_items'] = report.millify(total_items)
        data['total_sale'] = report.millify(total_sale)
        data['total_profit'] = report.millify(total_profit)
        return data

    def get_compare_charts_data(self, all_orders, interval, compare):
        val, period = compare.split('_')

        ranges = []
        now = timezone.now()

        dataset_labels = None
        data = None

        if period == 'week':
            ds_l = []
            e_day = now
            for i in range(int(val)):
                ds_l.append('Week {}'.format(i + 1))
                if e_day.weekday() == 0:
                    e_day = e_day - timedelta(days=1)
                s_day = e_day
                while s_day.weekday() > 0:
                    s_day -= timedelta(days=1)
                ranges.insert(0, [s_day, e_day])
                e_day = s_day - timedelta(days=1)
            dataset_labels = ds_l
        elif period == 'month':
            ds_l = []
            e_day = now
            for i in range(int(val)):
                s_day = e_day.replace(day=1)
                ds_l.insert(0, s_day.strftime('%B'))
                ranges.insert(0, [s_day, e_day])
                e_day = s_day - timedelta(days=1)
            dataset_labels = ds_l
        elif period == 'year':
            ds_l = []
            e_day = now
            for i in range(int(val)):
                s_day = e_day.replace(month=1, day=1)
                ds_l.insert(0, s_day.strftime('%Y'))
                ranges.insert(0, [s_day, e_day])
                e_day = s_day - timedelta(days=1)
            dataset_labels = ds_l

        all_orders = PLSOrder.objects.all().prefetch_related('order_items')

        if interval == 'day':
            order_count_data = []
            order_cost_data = []
            pls_sale_data = []
            gross_profit_data = []
            label_data = None
            for t_range in ranges:
                order_count_compare_data = []
                order_cost_compare_data = []
                pls_sale_compare_data = []
                gross_profit_compare_data = []
                lables = []
                start_at, end_at = t_range
                while start_at <= end_at:
                    filtered_orders = list(
                        filter(
                            lambda order: self.check_day_interval(order, start_at),
                            list(all_orders)
                        )
                    )
                    day_order_count = len(filtered_orders)
                    day_order_cost = sum(order.amount for order in filtered_orders)
                    order_items = []
                    for order in filtered_orders:
                        order_items += list(order.order_items.all())
                    day_pls_sale = sum(item.quantity for item in order_items)
                    order_count_compare_data.append(day_order_count)
                    order_cost_compare_data.append(
                        day_order_cost / 100.0 if day_order_cost else 0
                    )
                    pls_sale_compare_data.append(
                        day_pls_sale if day_pls_sale else 0
                    )
                    gross_profit_compare_data.append(
                        sum(((order.amount - order.wholesale_price) / 100.) for order in filtered_orders)
                    )
                    lables.append(start_at.strftime('%A') if period == 'week' else start_at.strftime('%d'))
                    start_at = start_at + timedelta(days=1)
                if not label_data:
                    label_data = lables
                elif len(label_data) < len(lables):
                    label_data = lables
                order_count_data.append(order_count_compare_data)
                order_cost_data.append(order_cost_compare_data)
                pls_sale_data.append(pls_sale_compare_data)
                gross_profit_data.append(gross_profit_compare_data)
            data = {
                'order_count_data': {
                    'data': order_count_data,
                    'label_data': label_data,
                    'dataset_label': dataset_labels
                },
                'order_cost_data': {
                    'data': order_cost_data,
                    'label_data': label_data,
                    'dataset_label': dataset_labels
                },
                'pls_sale_data': {
                    'data': pls_sale_data,
                    'label_data': label_data,
                    'dataset_label': dataset_labels
                },
                'gross_profit_data': {
                    'data': gross_profit_data,
                    'label_data': label_data,
                    'dataset_label': dataset_labels
                }
            }
        elif interval == 'month':
            order_count_data = []
            order_cost_data = []
            pls_sale_data = []
            gross_profit_data = []
            label_data = None
            for t_range in ranges:
                order_count_compare_data = []
                order_cost_compare_data = []
                pls_sale_compare_data = []
                gross_profit_compare_data = []
                lables = []
                start_at, end_at = t_range
                while start_at < end_at:
                    next_start = start_at + timedelta(days=report.get_days_in_month(start_at) - 1)
                    filtered_orders = list(
                        filter(
                            lambda order: self.check_range_interval(order, start_at, next_start),
                            list(all_orders)
                        )
                    )
                    day_order_count = len(filtered_orders)
                    day_order_cost = sum(order.amount for order in filtered_orders)
                    order_items = []
                    for order in filtered_orders:
                        order_items += list(order.order_items.all())
                    day_pls_sale = sum(item.quantity for item in order_items)
                    order_count_compare_data.append(day_order_count)
                    order_cost_compare_data.append(
                        day_order_cost / 100.0 if day_order_cost else 0
                    )
                    pls_sale_compare_data.append(
                        day_pls_sale if day_pls_sale else 0
                    )
                    gross_profit_compare_data.append(
                        sum(((order.amount - order.wholesale_price) / 100.) for order in filtered_orders)
                    )
                    lables.append(start_at.strftime('%B'))
                    start_at = next_start + timedelta(days=1)
                if not label_data:
                    label_data = lables
                elif len(label_data) < len(lables):
                    label_data = lables
                order_count_data.append(order_count_compare_data)
                order_cost_data.append(order_cost_compare_data)
                pls_sale_data.append(pls_sale_compare_data)
                gross_profit_data.append(gross_profit_compare_data)
            data = {
                'order_count_data': {
                    'data': order_count_data,
                    'label_data': label_data,
                    'dataset_label': dataset_labels
                },
                'order_cost_data': {
                    'data': order_cost_data,
                    'label_data': label_data,
                    'dataset_label': dataset_labels
                },
                'pls_sale_data': {
                    'data': pls_sale_data,
                    'label_data': label_data,
                    'dataset_label': dataset_labels
                },
                'gross_profit_data': {
                    'data': gross_profit_data,
                    'label_data': label_data,
                    'dataset_label': dataset_labels
                }
            }
        else:
            order_count_data = []
            order_cost_data = []
            pls_sale_data = []
            gross_profit_data = []
            label_data = None
            for t_range in ranges:
                order_count_compare_data = []
                order_cost_compare_data = []
                pls_sale_compare_data = []
                gross_profit_compare_data = []
                lables = []
                start_at, end_at = t_range
                count = 1
                while start_at < end_at:
                    next_start = start_at + timedelta(days=7)
                    filtered_orders = list(
                        filter(
                            lambda order: self.check_range_interval(order, start_at, next_start),
                            list(all_orders)
                        )
                    )
                    day_order_count = len(filtered_orders)
                    day_order_cost = sum(order.amount for order in filtered_orders)
                    order_items = []
                    for order in filtered_orders:
                        order_items += list(order.order_items.all())
                    day_pls_sale = sum(item.quantity for item in order_items)
                    order_count_compare_data.append(day_order_count)
                    order_cost_compare_data.append(
                        day_order_cost / 100.0 if day_order_cost else 0
                    )
                    pls_sale_compare_data.append(
                        day_pls_sale if day_pls_sale else 0
                    )
                    gross_profit_compare_data.append(
                        sum(((order.amount - order.wholesale_price) / 100.) for order in filtered_orders)
                    )
                    lables.append('Week {}'.format(count))
                    if count == 4:
                        count = 1
                    else:
                        count += 1
                    start_at = next_start + timedelta(days=1)
                if not label_data:
                    label_data = lables
                elif len(label_data) < len(lables):
                    label_data = lables
                order_count_data.append(order_count_compare_data)
                order_cost_data.append(order_cost_compare_data)
                pls_sale_data.append(pls_sale_compare_data)
                gross_profit_data.append(gross_profit_compare_data)
            data = {
                'order_count_data': {
                    'data': order_count_data,
                    'label_data': label_data,
                    'dataset_label': dataset_labels
                },
                'order_cost_data': {
                    'data': order_cost_data,
                    'label_data': label_data,
                    'dataset_label': dataset_labels
                },
                'pls_sale_data': {
                    'data': pls_sale_data,
                    'label_data': label_data,
                    'dataset_label': dataset_labels
                },
                'gross_profit_data': {
                    'data': gross_profit_data,
                    'label_data': label_data,
                    'dataset_label': dataset_labels
                }
            }

        avg_order_count_data = []
        avg_order_label_data = None
        for t_range in ranges:
            count = 1
            avg_compare_data = []
            lables = []
            start_at, end_at = t_range
            while start_at < end_at:
                if start_at.weekday() > 0:
                    next_start = start_at + timedelta(days=(6 - start_at.weekday()))
                else:
                    next_start = start_at + timedelta(days=6)
                filtered_orders = list(
                    filter(
                        lambda order: self.check_range_interval(order, start_at, next_start),
                        list(all_orders)
                    )
                )
                day_order_count = len(filtered_orders)
                num_days = (next_start - start_at).days + 1
                avg_compare_data.append(round(day_order_count / num_days, 2))
                lables.append('Week {}'.format(count))
                start_at = next_start + timedelta(days=1)
                if count == 4:
                    count = 1
                else:
                    count += 1
            if not avg_order_label_data:
                avg_order_label_data = lables
            elif len(avg_order_label_data) < len(lables):
                avg_order_label_data = lables
            avg_order_count_data.append(avg_compare_data)
        data['avg_order_data'] = {
            'data': avg_order_count_data,
            'label_data': avg_order_label_data,
            'dataset_label': dataset_labels
        }

        all_sku = []
        sku_data = []
        all_title = []
        all_link = []
        for t_range in ranges:
            compare_sku = []
            compare_sku_data = []
            start_at, end_at = t_range
            filtered_orders = list(
                filter(
                    lambda order: self.check_range_interval(order, start_at, end_at),
                    list(all_orders)
                )
            )
            for order in filtered_orders:
                for line_item in order.order_items.all():
                    sku = line_item.label.user_supplement.pl_supplement.shipstation_sku
                    title = line_item.label.user_supplement.pl_supplement.title
                    pl_link = reverse('pls:supplement', kwargs={'supplement_id': line_item.label.user_supplement.id})
                    if sku not in all_sku:
                        all_sku.append(sku)
                        all_title.append(title)
                        all_link.append(pl_link)
                    if sku not in compare_sku:
                        compare_sku.append(sku)
                        compare_sku_data.append(line_item.quantity)
                    else:
                        prev_val = compare_sku_data[compare_sku.index(sku)]
                        compare_sku_data[compare_sku.index(sku)] = prev_val + line_item.quantity
            final_compare_data = []
            for sku in all_sku:
                if sku not in compare_sku:
                    compare_sku.append(sku)
                    compare_sku_data.append(0)
                final_compare_data.append(
                    compare_sku_data[compare_sku.index(sku)]
                )
            sku_data.append(final_compare_data)
        for block_index, block_c_data in enumerate(sku_data):
            if len(block_c_data) < len(all_sku):
                reps = len(all_sku) - len(block_c_data)
                for i in range(reps):
                    sku_data[block_index].append(0)
        if sku_data:
            all_sku, sku_data, all_title, all_link = report.sort_sku_data(
                all_sku,
                sku_data,
                all_title,
                all_link
            )
        data['pls_sku_data'] = {
            'data': sku_data,
            'label_data': all_sku,
            'dataset_label': dataset_labels,
            'title_data': all_title,
            'link_data': all_link
        }

        total_amount = 0
        total_cost = 0
        total_shipping_cost = 0
        total_orders = 0
        total_items = 0
        total_sale = 0
        total_profit = 0
        for t_range in ranges:
            start_at, end_at = t_range
            filtered_orders = list(
                filter(
                    lambda order: self.check_range_interval(order, start_at, end_at),
                    list(all_orders)
                )
            )
            total_amount += sum(order.amount for order in filtered_orders)
            total_cost += sum(order.wholesale_price for order in filtered_orders)
            total_shipping_cost += sum(order.shipping_price for order in filtered_orders)
            total_orders += len(filtered_orders)
            order_items = []
            for order in filtered_orders:
                order_items += list(order.order_items.all())
            total_items += sum(item.quantity for item in order_items)
            total_sale += sum(order.sale_price for order in filtered_orders) / 100.
            total_profit += sum((order.sale_price - order.amount) for order in filtered_orders) / 100.
        gross_profit = (total_amount - (total_cost + total_shipping_cost)) / 100.
        total_revenue = total_amount / 100.

        data['gross_profit'] = report.millify(gross_profit)
        data['revenue'] = report.millify(total_revenue)
        data['total_orders'] = report.millify(total_orders)
        data['total_items'] = report.millify(total_items)
        data['total_sale'] = report.millify(total_sale)
        data['total_profit'] = report.millify(total_profit)
        return data

    def validate_compare_interval(self, compare, interval):
        val, period = compare.split('_')
        if interval == 'day' and period == 'year':
            return 'week'
        elif interval == 'month' and period == 'week':
            return 'day'
        elif interval == 'month' and period == 'month':
            return 'week'
        elif interval == 'week' and period == 'week':
            return 'day'
        else:
            return interval

    def validate_interval(self, start_at, end_at, interval):
        if interval == 'day' and (end_at - start_at).days > 60:
            return 'week'
        if interval == 'month' and (end_at - start_at).days < 120:
            if (end_at - start_at).days < 60:
                return 'day'
            else:
                return 'week'
        else:
            return interval

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        charts_data = None

        interval = None

        all_orders = PLSOrder.objects.all().prefetch_related(
            'order_items',
            'order_items__label',
            'order_items__label__user_supplement',
            'order_items__label__user_supplement__pl_supplement'
        )

        form = self.form(self.request.GET)
        if form.is_valid():
            cd = form.cleaned_data
            period = cd['period']
            start_date = cd['start_date']
            end_date = cd['end_date']
            compare = cd['compare']

            interval = cd['interval']
            now = timezone.now()

            if period:
                if period == 'week':
                    start_at = now - timedelta(days=6)
                    end_at = now
                    interval = self.validate_interval(start_at, end_at, interval)
                    charts_data = self.get_charts_data(all_orders, interval, start_at, end_at)
                elif period == 'month':
                    start_at = now.replace(day=1)
                    end_at = now
                    interval = self.validate_interval(start_at, end_at, interval)
                    charts_data = self.get_charts_data(all_orders, interval, start_at, end_at)
                elif period == 'year':
                    start_at = now.replace(month=1, day=1)
                    end_at = now
                    interval = self.validate_interval(start_at, end_at, interval)
                    charts_data = self.get_charts_data(all_orders, interval, start_at, end_at)
            else:
                if start_date and end_date:
                    start_at = datetime.combine(start_date, datetime.min.time())
                    end_at = datetime.combine(end_date, datetime.min.time())
                    interval = self.validate_interval(start_at, end_at, interval)
                    charts_data = self.get_charts_data(all_orders, interval, start_at, end_at)
                else:
                    if compare:
                        interval = self.validate_compare_interval(compare, interval)
                        charts_data = self.get_compare_charts_data(all_orders, interval, compare)
                    else:
                        interval = 'day'
                        start_at = now - timedelta(days=6)
                        end_at = now
                        charts_data = self.get_charts_data(all_orders, interval, start_at, end_at)
                        cd['period'] = 'week'

            cd['interval'] = interval
            form = self.form(initial=cd)

        seller_track = []
        seller_data = []

        filtered_orders = list(
            filter(
                lambda order: self.check_range_interval(order, start_at, end_at),
                list(all_orders)
            )
        )

        for order in filtered_orders:
            d = {}
            d['user'] = order.user
            d['items_track'] = []
            d['items_data'] = []
            d['total_sales'] = order.amount / 100.
            for item in order.order_items.all():
                try:
                    d_index = d['items_track'].index(item.label)
                    d['items_data'][d_index]['q'] += item.quantity
                except:
                    d['items_track'].append(item.label)
                    d['items_data'].append({'item': item.label, 'q': item.quantity})
            try:
                m_index = seller_track.index(order.user)
                main = seller_data[m_index]
                main['total_sales'] += order.amount / 100.
                for i, item in enumerate(d['items_track']):
                    try:
                        m_i_index = main['items_track'].index(item)
                        main['items_data'][m_i_index]['q'] += d['items_data'][i]['q']
                    except:
                        main['items_track'].append(item)
                        main['items_data'].append(d['items_data'][i])
                seller_data[m_index] = main
            except:
                seller_track.append(order.user)
                seller_data.append(d)

        seller_data.sort(key=report.sort_seller, reverse=True)
        seller_data = seller_data[:10]
        for seller in seller_data:
            seller['total_items'] = sum(item['q'] for item in seller['items_data'])
            seller.pop('items_track')
            seller['items_data'].sort(key=report.sort_items, reverse=True)
            seller['items_data'] = seller['items_data'][:5]

        context.update({
            'breadcrumbs': self.get_breadcrumbs(),
            'form': form,
            'gross_profit': charts_data.pop('gross_profit'),
            'revenue': charts_data.pop('revenue'),
            'total_orders': int(charts_data.pop('total_orders')),
            'total_items': int(charts_data.pop('total_items')),
            'total_sale': charts_data.pop('total_sale'),
            'total_profit': charts_data.pop('total_profit'),
            'charts_data': escapejs(mark_safe(json.dumps(charts_data))),
            'seller_data': seller_data
        })
        return context


class Basket(LoginRequiredMixin, TemplateView):

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        # Permission check
        if request.user.can('supplements_basket.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get(self, request):
        breadcrumbs = [
            {'title': 'Supplements', 'url': reverse('pls:index')},
            {'title': 'My Basket', 'url': reverse('pls:my_basket')},
        ]

        basket_items = request.user.basket_items.all()

        context = {
            'breadcrumbs': breadcrumbs,
            'basket_items': basket_items,
        }

        return render(request, "supplements/userbasket.html", context)


class BasketCheckout(LoginRequiredMixin, TemplateView):

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        # Permission check
        if request.user.can('supplements_basket.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get(self, request):
        breadcrumbs = [
            {'title': 'Supplements', 'url': reverse('pls:index')},
            {'title': 'Checkout', 'url': reverse('pls:checkout')},
        ]

        basket_items = request.user.basket_items.all()
        checkout_total = 0
        for basket_item in basket_items:
            checkout_total += safe_float(basket_item.total_price())
        user = request.user

        context = {
            'breadcrumbs': breadcrumbs,
            'basket_items': basket_items,
            'countries': get_counrties_list(),
            'user': user,
            'checkout_total': '%.02f' % checkout_total
        }

        return render(request, "supplements/basket_ckeckout.html", context)
