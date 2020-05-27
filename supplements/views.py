import csv
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db import transaction, models
from django.db.models import Q
from django.db.models.functions import Concat
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView
from django.views.generic.list import ListView
from django import template

import bleach
import requests
import simplejson as json
from barcode import generate
from pdfrw import PageMerge, PdfReader, PdfWriter
from product_common import views as common_views
from product_common.lib import views as common_lib_views
from product_common.lib.views import PagingMixin, upload_image_to_aws, upload_object_to_aws
from product_common.models import ProductImage
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg

from shopified_core import permissions
from shopified_core.utils import aws_s3_context as images_aws_s3_context, safe_int
from shopified_core.shipping_helper import get_counrties_list
from shopified_core.utils import app_link
from supplements.lib.authorizenet import create_customer_profile, create_payment_profile
from supplements.lib.image import get_order_number_label
from supplements.models import (
    AuthorizeNetCustomer,
    Payout,
    PLSOrder,
    PLSOrderLine,
    PLSupplement,
    ShippingGroup,
    UserSupplement,
    UserSupplementImage,
    UserSupplementLabel,
    SUPPLEMENTS_SUPPLIER,
)

from .forms import (
    BillingForm,
    CommentForm,
    LabelFilterForm,
    AllLabelFilterForm,
    LineFilterForm,
    MyOrderFilterForm,
    OrderFilterForm,
    PayoutFilterForm,
    PayoutForm,
    PLSupplementEditForm,
    PLSupplementForm,
    PLSupplementFilterForm,
    UploadJSONForm,
    UserSupplementForm,
    UserSupplementFilterForm
)
from .utils import aws_s3_context, create_rows, send_email_against_comment, payment

register = template.Library()


class Index(common_views.IndexView):
    model = PLSupplement

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.profile.is_black or request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_queryset(self):
        queryset = super().get_queryset()

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
        return [{'title': 'Supplements', 'url': reverse('pls:index')}]

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['supplements'] = context['products']
        context['form'] = PLSupplementFilterForm(self.request.GET)
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
            {'title': 'Supplements Admin', 'url': reverse('pls:all_labels')},
            {'title': 'Add New Supplement', 'url': reverse('pls:product')},
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
            {'title': 'Supplements Admin', 'url': reverse('pls:all_labels')},
            {'title': 'Edit Supplement', 'url': reverse('pls:product_edit', kwargs=kwargs)},
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
        form_data['authenticity_certificate_url'] = self.supplement.authenticity_certificate_url

        context = {
            'breadcrumbs': self.get_breadcrumbs(supplement_id),
            'form': self.form(initial=form_data, instance=self.supplement),
        }
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
        if request.user.profile.is_black or request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_api_data(self, user_supplement):
        data = user_supplement.to_dict()

        kwargs = {'supplement_id': user_supplement.id}
        original_url = reverse('pls:user_supplement', kwargs=kwargs)
        data['original_url'] = self.request.build_absolute_uri(original_url)
        data['user_supplement_id'] = user_supplement.id

        api_data = {}
        if user_supplement.current_label.is_approved:
            api_data = self.serialize_api_data(data)

        return api_data

    def serialize_api_data(self, data):
        return json.dumps(dict(
            title=data['title'],
            description=data['description'],
            type=data['category'],
            vendor=SUPPLEMENTS_SUPPLIER,
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
                name=SUPPLEMENTS_SUPPLIER,
                url='',
            ),
        ), use_decimal=True)


class LabelMixin:
    def save_label(self, user, url, user_supplement):
        new_label = user_supplement.labels.create(url=url)

        if user_supplement.current_label:
            reverse_url = reverse('pls:label_detail', kwargs={
                'label_id': user_supplement.current_label.id
            })
            comment = (f"There is an <a href='{reverse_url}'>"
                       f"older version</a> of this label.")
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
        barcode_obj.scale(0.3, 0.7)
        barcode_obj.x = barcode_obj.y = 8

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
        if request.user.profile.is_black or request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self, supplement_id):
        url = reverse('pls:supplement',
                      kwargs={'supplement_id': supplement_id})
        breadcrumbs = [
            {'title': 'Supplements', 'url': reverse('pls:index')},
            {'title': 'Supplement', 'url': url},
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

    def get_supplement_data(self, user, supplement_id):
        supplement = self.get_supplement(user, supplement_id)

        form_data = supplement.to_dict()
        form_data['action'] = 'save'
        form_data['shipping_countries'] = supplement.shipping_groups_string
        form_data['label_size'] = supplement.label_size
        form_data['mockup_type'] = supplement.mockup_type
        form_data['mockup_slug'] = supplement.mockup_type.slug
        form_data['weight'] = supplement.weight
        form_data['inventory'] = supplement.inventory
        form_data['msrp'] = supplement.msrp
        form_data['label_presets'] = json.dumps(supplement.mockup_type.get_label_presets())

        api_data = {}
        if supplement.is_approved:
            api_data = self.get_api_data(supplement)

        store_type_and_data = self.get_store_data(user)

        data = dict(
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
                and new_user_supplement.current_label.status != UserSupplementLabel.DRAFT
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
                url = reverse("pls:my_labels") + "?s=1"
                return redirect(url)

            kwargs = {'supplement_id': new_user_supplement.id}
            return self.get_redirect_url(**kwargs)

        context = self.get_supplement_data(user, self.supplement_id)

        context['form'] = form
        context['breadcrumbs'] = self.get_breadcrumbs(self.supplement_id)

        return render(request, "supplements/supplement.html", context)

    def get_redirect_url(self, *args, **kwargs):
        return redirect(reverse("pls:user_supplement", kwargs=kwargs))

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
        if request.user.profile.is_black or request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self, supplement_id):
        url = reverse('pls:user_supplement',
                      kwargs={'supplement_id': supplement_id})
        breadcrumbs = [
            {'title': 'Supplements', 'url': reverse('pls:index')},
            {'title': 'User Supplement', 'url': url},
        ]
        return breadcrumbs

    def get_supplement_data(self, user, supplement_id):
        supplement = self.get_supplement(user, supplement_id)

        form_data = supplement.to_dict()
        form_data['action'] = 'save'
        form_data['shipping_countries'] = supplement.shipping_groups_string
        form_data['label_size'] = supplement.pl_supplement.label_size
        form_data['mockup_type'] = supplement.pl_supplement.mockup_type
        form_data['mockup_slug'] = supplement.pl_supplement.mockup_type.slug
        form_data['weight'] = supplement.pl_supplement.weight
        form_data['inventory'] = supplement.pl_supplement.inventory
        form_data['label_presets'] = supplement.get_label_presets_json()

        api_data = {}
        if supplement.is_approved:
            api_data = self.get_api_data(supplement)

        store_type_and_data = self.get_store_data(user)
        status_url = None
        is_submitted = False
        if supplement.current_label:
            status_url = reverse('pls:label_detail',
                                 kwargs={'label_id': supplement.current_label.id})
            is_submitted = supplement.current_label.status != UserSupplementLabel.DRAFT

        data = dict(
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
            status_url=status_url,
            is_submitted=is_submitted,
            mockup_layers=supplement.pl_supplement.mockup_type.get_layers(),
        )

        if 'label_url' in form_data:
            data['label_url'] = form_data.pop('label_url')

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


class MySupplements(LoginRequiredMixin, View):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.profile.is_black or request.user.can('pls.use'):
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
            {'title': 'Supplements', 'url': reverse('pls:index')},
            {'title': 'My Supplements', 'url': reverse('pls:my_supplements')},
        ]
        form = UserSupplementFilterForm(self.request.GET)
        queryset = request.user.models_user.pl_supplements.filter(pl_supplement__is_active=True).exclude(is_deleted=True)

        if form.is_valid():
            queryset = self.add_filters(queryset, form)

        len_supplement = len(queryset)
        if len_supplement == 1:
            len_supplement = "1 supplement."
        elif len_supplement > 0:
            len_supplement = f"{len_supplement} supplements."

        supplements = [i for i in queryset]

        context = {
            'breadcrumbs': breadcrumbs,
            'supplements': create_rows(supplements, 4),
            'form': UserSupplementFilterForm(self.request.GET),
            'count': len_supplement
        }
        return render(request, "supplements/userproduct.html", context)


class MyLabels(LoginRequiredMixin, ListView, PagingMixin):
    paginate_by = 20
    ordering = '-updated_at'
    template_name = 'supplements/my_labels.html'
    model = UserSupplementLabel

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.profile.is_black or request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Supplements', 'url': reverse('pls:index')},
            {'title': 'My Labels', 'url': reverse('pls:my_labels')},
        ]

    def add_filters(self, queryset):
        user = self.request.user.models_user
        queryset = queryset.filter(user_supplement__user=user)
        queryset = queryset.filter(current_label_of__isnull=False)
        return queryset

    def get_queryset(self):
        queryset = super().get_queryset().exclude(status=UserSupplementLabel.DRAFT)
        queryset = self.add_filters(queryset)

        form = self.form = LabelFilterForm(self.request.GET)
        if form.is_valid():
            status = form.cleaned_data['status']
            if status:
                queryset = queryset.filter(status=status)

            sku = form.cleaned_data['sku']
            if sku:
                queryset = queryset.filter(sku=sku)

            created_at = form.cleaned_data['date']
            if created_at:
                queryset = queryset.filter(created_at__date=created_at)

        return queryset

    def get_label_comment_count(self, label):
        len_comment = label.comments.count()
        if len_comment == 1:
            return "1 comment"
        else:
            return f"{len_comment} comments"

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        self.add_paging_context(context)

        len_label = context['paginator'].count
        if len_label == 1:
            label_count = "1 label."
        else:
            label_count = f"{len_label} labels."

        context.update({
            'breadcrumbs': self.get_breadcrumbs(),
            'label_count': label_count,
            'labels': context['object_list'],
            'show_alert': self.request.GET.get('s') == '1',
            'form': self.form,
        })
        return context


class AllLabels(MyLabels):
    template_name = 'supplements/all_labels.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_ordering(self):
        order_by = self.request.GET.get('sort', '-updated_at')
        allowed_values = ['updated_at', '-updated_at']
        if order_by not in allowed_values:
            order_by = '-updated_at'
        return order_by

    def add_filters(self, queryset):
        return queryset

    def get_breadcrumbs(self):
        return [
            {'title': 'Supplements Admin', 'url': reverse('pls:all_labels')},
            {'title': 'All Labels', 'url': reverse('pls:all_labels')},
        ]

    def get_queryset(self):
        queryset = super().get_queryset()

        form = AllLabelFilterForm(self.request.GET)
        if form.is_valid():
            label_user_name = form.cleaned_data['label_user_name']
            if label_user_name:
                queryset = queryset.annotate(
                    name=Concat('user_supplement__user__first_name', models.Value(' '), 'user_supplement__user__last_name')
                ).filter(
                    Q(user_supplement__user__email__icontains=label_user_name)
                    | Q(user_supplement__user_id=safe_int(label_user_name, None))
                    | Q(name__icontains=label_user_name)
                )

            product_sku = form.cleaned_data['product_sku']
            if product_sku:
                queryset = queryset.filter(user_supplement__pl_supplement__shipstation_sku__iexact=product_sku)

            title = form.cleaned_data['title']
            if title:
                queryset = queryset.filter(user_supplement__pl_supplement__title__icontains=title)

        return queryset

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['all_label_form'] = AllLabelFilterForm(self.request.GET)
        return context


def upload_supplement_object_to_aws(user_supplement, obj, name):
    # Randomize filename in order to not overwrite an existing file
    path = f'uploads/u{user_supplement.user.id}/pls_label/{user_supplement.id}'
    return upload_object_to_aws(path, name, obj)


class Label(LabelMixin, LoginRequiredMixin, View, SendToStoreMixin):

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.profile.is_black or request.user.can('pls.use'):
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
            {'title': 'Supplements', 'url': reverse('pls:index')},
            {'title': user_supplement.title, 'url': user_supplement_url},
            {'title': 'Label', 'url': self.request.path},
        ]

    def get_context_data(self, *args, **kwargs):
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
            breadcrumbs=self.get_breadcrumbs(),
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

    @transaction.atomic
    def post(self, request, label_id):
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            self.label = label = get_object_or_404(UserSupplementLabel, id=label_id)
        else:
            self.label = label = get_object_or_404(UserSupplementLabel, id=label_id, user_supplement__user=request.user.models_user)

        user_supplement = label.user_supplement
        comments = label.comments

        user = request.user
        user_name = user.get_full_name()

        kwargs = {'label_id': label_id}
        reverse_url = reverse('pls:label_detail', kwargs=kwargs)

        action = request.POST['action']
        form = CommentForm()

        if action == 'comment':
            form = CommentForm(request.POST)
            if form.is_valid():
                comment = form.cleaned_data['comment']
                if comment:
                    is_private = form.cleaned_data['is_private']
                    self.create_comment(comments, comment, is_private=is_private)

                # Restart review process for new labels
                upload_url = form.cleaned_data['upload_url']
                if upload_url:
                    user_supplement.label_presets = request.POST.get('label_presets') or '{}'
                    self.save_label(user, upload_url, user_supplement)
                    user_supplement.current_label.status = UserSupplementLabel.AWAITING_REVIEW
                    user_supplement.current_label.save()

                # Old images should be removed when new label is uploaded
                mockup_urls = request.POST.getlist('mockup_urls')
                if len(mockup_urls) or upload_url:
                    user_supplement.images.all().delete()
                    for position, mockup_url in enumerate(mockup_urls):
                        user_supplement.images.create(image_url=mockup_url, position=position)

                return redirect(reverse('pls:label_detail', kwargs={
                    'label_id': user_supplement.current_label.id
                }))

        elif action in (label.APPROVED, label.REJECTED):
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

            comment = (f"<strong>{user_name}</strong> set the status to "
                       f"<span class='label {label_class}'>"
                       f"{label.status_string}</span>")
            self.create_comment(comments, comment, new_status=action)
            return redirect(reverse_url)

        context = self.get_context_data(label=label)
        context.update({
            'form': form,
            'comments': comments.all().order_by('-created_at'),
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

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Supplements Admin', 'url': reverse('pls:all_labels')},
            {'title': 'Payments', 'url': reverse('pls:order_list')},
        ]

    def get_queryset(self):
        queryset = super().get_queryset()

        form = self.form
        if form.is_valid():
            reference_number = form.cleaned_data['refnum']
            if reference_number:
                queryset = queryset.filter(
                    payout__reference_number=reference_number
                )

        return queryset


class OrderDetailMixin(LoginRequiredMixin, View):
    def get_breadcrumbs(self, order):
        return [
            {'title': 'Supplements Admin', 'url': reverse('pls:all_labels')},
            {'title': 'Payments', 'url': reverse('pls:order_list')},
            {'title': order.order_number, 'url': reverse('pls:order_detail', kwargs={'order_id': order.id})}
        ]

    def get_context_data(self, *args, **kwargs):
        order = kwargs['order']

        line_items = [dict(
            id=i.id,
            sku=i.label.sku,
            quantity=i.quantity,
            supplement=i.label.user_supplement.to_dict()
        ) for i in order.order_items.all()]

        util = payment.Util()
        store = util.get_store(order.store_id, order.store_type)

        if not self.request.user.can('pls_admin.use') and not self.request.user.can('pls_staff.use'):
            # Make sure this user have access to this order store
            permissions.user_can_view(self.request.user, store)

        util.store = store
        shipping_address = util.get_order(order.store_order_id).get('shipping_address')

        return dict(
            order=order.order_number,
            payment_id=order.stripe_transaction_id,
            total_price=order.amount_string,
            sale_price=order.sale_price_string,
            user_profit=order.user_profit_string,
            shipping_address=shipping_address,
            shipping_price=order.shipping_price_string,
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
        if request.user.profile.is_black or request.user.can('pls.use'):
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
        if request.user.profile.is_black or request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Supplements', 'url': reverse('pls:index')},
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

            stripe_id = form.cleaned_data['stripe_id']
            if stripe_id:
                queryset = queryset.filter(stripe_transaction_id=stripe_id)

            created_at = form.cleaned_data['date']
            if created_at:
                queryset = queryset.filter(created_at__date=created_at)

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
    add_form = PayoutForm
    order_class = PLSOrder

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Supplements Admin', 'url': reverse('pls:all_labels')},
            {'title': 'Payouts', 'url': reverse('pls:payout_list')},
        ]

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        add_form = getattr(self, 'add_form', False)
        context['add_form'] = add_form or add_form()
        return context

    def post(self, request):
        self.add_form = form = self.add_form(request.POST)
        if form.is_valid():
            ref_number = form.cleaned_data['reference_number']
            with transaction.atomic():
                payout = self.model.objects.create(reference_number=ref_number)
                orders = self.order_class.objects.filter(
                    is_fulfilled=True,
                    payout__isnull=True,
                )
                for order in orders:
                    order.payout = payout
                    order.save()

            return redirect(request.path)

        return self.get(request)


class OrderItemListView(common_views.OrderItemListView):
    model = PLSOrderLine
    paginate_by = 20
    ordering = '-created_at'
    filter_form = LineFilterForm
    namespace = 'pls'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use') or request.user.can('pls_staff.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Supplements Admin', 'url': reverse('pls:all_labels')},
            {'title': 'Order Items', 'url': reverse('pls:orderitem_list')},
        ]


class GenerateLabel(LoginRequiredMixin, View):
    def get(self, request, line_id):
        line_item = get_object_or_404(PLSOrderLine, id=line_id)
        base_label_pdf = get_order_number_label(line_item)

        output = BytesIO()
        PdfWriter().write(output, base_label_pdf)

        output.seek(0)
        return HttpResponse(output.read(), content_type='application/pdf')


class Billing(LoginRequiredMixin, TemplateView):
    template_name = 'supplements/billing.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.profile.is_black or request.user.can('pls.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_context_data(self, *args, **kwargs):
        try:
            self.request.user.authorize_net_customer.retrieve()
        except AuthorizeNetCustomer.DoesNotExist:
            pass

        return super().get_context_data(
            countries=get_counrties_list(),
            *args,
            **kwargs,
        )

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
        if request.user.profile.is_black or request.user.can('pls.use'):
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
        if request.user.can('pls_admin.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_breadcrumbs(self):
        return [
            {'title': 'Supplements Admin', 'url': reverse('pls:all_labels')},
            {'title': 'Import / Export', 'url': reverse('pls:upload_json')},
        ]

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

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

            return redirect(reverse('pls:index'))
        return self.get(request)


class DownloadJSON(LoginRequiredMixin, View):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('pls_admin.use'):
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
