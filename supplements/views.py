from io import BytesIO

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.views import View
from django.views.generic import TemplateView
from django.views.generic.list import ListView

import bleach
import bleach.sanitizer
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

from leadgalaxy.models import ShopifyStore
from shopified_core.shipping_helper import get_counrties_list
from shopify_orders.models import ShopifyOrderLog
from supplements.lib.authorizenet import create_customer_profile, create_payment_profile
from supplements.lib.image import data_url_to_pil_image, get_bottle_mockup, get_order_number_label, pil_to_fp
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
    BillingForm,
    CommentForm,
    LabelFilterForm,
    LineFilterForm,
    MyOrderFilterForm,
    OrderFilterForm,
    PayoutFilterForm,
    PayoutForm,
    PLSupplementForm,
    UploadJSONForm,
    UserSupplementForm
)
from .utils import create_rows, send_email_against_comment


class Index(common_views.IndexView):
    model = PLSupplement

    def get_template(self):
        return 'supplements/index.html'

    def get_new_product_url(self):
        return reverse('pls:product')

    def get_breadcrumbs(self):
        return [{'title': 'PLS', 'url': reverse('pls:index')}]

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['supplements'] = context['products']
        return context


class Product(common_views.ProductAddView):
    form = PLSupplementForm
    namespace = 'pls'
    template_name = "supplements/product.html"

    def get_breadcrumbs(self):
        return [
            {'title': 'PLS', 'url': reverse('pls:index')},
            {'title': 'Add New Supplement', 'url': reverse('product')},
        ]

    def process_valid_form(self, form):
        request = self.request
        user_id = request.user.id

        template = request.FILES['template']
        template_url = upload_image_to_aws(template, 'pls_label', user_id)

        thumbnail = request.FILES['thumbnail']
        thumbnail_url = upload_image_to_aws(thumbnail, 'pls_image', user_id)

        certificate = request.FILES['authenticity_certificate']
        certificate_url = upload_image_to_aws(certificate, 'pls_certificate', user_id)

        pl_supplement = form.save(commit=False)
        pl_supplement.label_template_url = template_url
        pl_supplement.authenticity_certificate_url = certificate_url
        pl_supplement.save()
        form.save_m2m()

        pl_supplement.images.create(
            product=pl_supplement,
            position=0,
            image_url=thumbnail_url,
        )


class SendToStoreMixin(common_lib_views.SendToStoreMixin):
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
            vendor="PLSupplement",  # TODO: Confirm
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
                name="PLSupplement",
                url='',
            ),
        ), use_decimal=True)


class LabelMixin:
    def save_label(self, user, label, user_supplement):
        assert label.tell() == 0

        url = upload_supplement_object_to_aws(
            user_supplement,
            label,
            label.name,
        )

        new_label = user_supplement.labels.create(url=url)
        user_supplement.current_label = new_label
        user_supplement.save()


class Supplement(LabelMixin, LoginRequiredMixin, View, SendToStoreMixin):
    template_name = 'supplements/supplement.html'

    def get_breadcrumbs(self, supplement_id):
        url = reverse('pls:supplement',
                      kwargs={'supplement_id': supplement_id})
        breadcrumbs = [
            {'title': 'PLS', 'url': reverse('pls:index')},
            {'title': 'Supplement', 'url': url},
        ]
        return breadcrumbs

    def save_image(self, user, image, user_supplement):
        upload_url = upload_supplement_object_to_aws(
            user_supplement,
            image,
            image.name,
        )

        user_supplement.images.create(image_url=upload_url, position=1)

    def copy_images(self, user_supplement):
        current_urls = set(
            user_supplement.images.values_list('image_url', flat=True)
        )

        pls_images = ProductImage.objects.filter(
            product_id=user_supplement.pl_supplement_id)

        UserSupplementImage.objects.bulk_create([
            UserSupplementImage(position=i.position,
                                image_url=i.image_url,
                                user_supplement=user_supplement)
            for i in pls_images if i.image_url not in current_urls
        ])

    def get_supplement(self, user, supplement_id):
        return get_object_or_404(PLSupplement, id=supplement_id)

    def get_supplement_data(self, user, supplement_id):
        supplement = self.get_supplement(user, supplement_id)

        form_data = supplement.to_dict()
        form_data['action'] = 'save'
        form_data['shipping_countries'] = supplement.shipping_groups_string
        form_data['label_size'] = supplement.label_size

        api_data = {}
        if supplement.is_approved:
            api_data = self.get_api_data(supplement)

        store_type_and_data = self.get_store_data(user)

        data = dict(
            form_data=form_data,
            image_urls=form_data.pop('image_urls'),
            label_template_url=form_data.pop('label_template_url'),
            is_approved=supplement.is_approved,
            is_awaiting_review=supplement.is_awaiting_review,
            api_data=api_data,
            store_data=store_type_and_data['store_data'],
            store_types=store_type_and_data['store_types'],
            product_information=supplement.product_information,
            authenticity_cert=supplement.authenticity_certificate_url,
        )

        if 'label_url' in form_data:
            data['label_url'] = form_data.pop('label_url')

        return data

    def get_form(self):
        return UserSupplementForm(self.request.POST, self.request.FILES)

    def save_supplement(self, form):
        supplement = form.save(commit=False)
        supplement.pl_supplement_id = self.supplement_id
        supplement.user_id = self.request.user.id
        supplement.tags = form.cleaned_data['tags']
        supplement.save()
        return supplement

    def save(self, request):
        user = request.user
        form = self.get_form()
        if form.is_valid():
            new_user_supplement = self.save_supplement(form)

            self.copy_images(new_user_supplement)

            upload = request.FILES.get('upload')
            if upload:
                if form.cleaned_data['action'] == 'approve':
                    image_data = form.cleaned_data['image_data_url']
                    label_image = data_url_to_pil_image(image_data)
                    bottle_mockup = get_bottle_mockup(label_image)
                    image_fp = pil_to_fp(bottle_mockup)
                    image_fp.seek(0)
                    image_fp.name = 'mockup.png'

                    self.save_label(user, upload, new_user_supplement)
                    self.save_image(user, image_fp, new_user_supplement)
                    url = reverse("pls:my_labels") + "?s=1"
                    return redirect(url)
                else:
                    self.save_image(user, upload, new_user_supplement)

            kwargs = {'supplement_id': new_user_supplement.id}
            return self.get_redirect_url(**kwargs)

        context = self.get_supplement_data(user, self.supplement_id)

        context['form'] = form
        context['breadcrumbs'] = self.get_breadcrumbs(self.supplement_id)

        return render(request, "supplements/supplement.html", context)

    def get_redirect_url(self, *args, **kwargs):
        return redirect(reverse("pls:user_supplement", kwargs=kwargs))

    def get(self, request, supplement_id):
        context = self.get_supplement_data(request.user, supplement_id)

        context.update({
            'breadcrumbs': self.get_breadcrumbs(supplement_id),
            'form': UserSupplementForm(initial=context['form_data']),
        })
        return render(request, self.template_name, context)

    def post(self, request, supplement_id):
        self.supplement_id = supplement_id
        return self.save(request)


class UserSupplementView(Supplement):
    template_name = 'supplements/user_supplement.html'

    def get_breadcrumbs(self, supplement_id):
        url = reverse('pls:user_supplement',
                      kwargs={'supplement_id': supplement_id})
        breadcrumbs = [
            {'title': 'PLS', 'url': reverse('pls:index')},
            {'title': 'User Supplement', 'url': url},
        ]
        return breadcrumbs

    def get_supplement_data(self, user, supplement_id):
        supplement = self.get_supplement(user, supplement_id)

        form_data = supplement.to_dict()
        form_data['action'] = 'save'
        form_data['shipping_countries'] = supplement.shipping_groups_string
        form_data['label_size'] = supplement.pl_supplement.label_size

        api_data = {}
        if supplement.is_approved:
            api_data = self.get_api_data(supplement)

        store_type_and_data = self.get_store_data(user)

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
        )

        if 'label_url' in form_data:
            data['label_url'] = form_data.pop('label_url')

        return data

    def get_form(self):
        user_supplement = UserSupplement.objects.get(id=self.supplement_id)
        return UserSupplementForm(self.request.POST,
                                  self.request.FILES,
                                  instance=user_supplement)

    def get_supplement(self, user, supplement_id):
        return get_object_or_404(UserSupplement, id=supplement_id)

    def save_supplement(self, form):
        return form.save()


class MySupplements(LoginRequiredMixin, View):
    def get(self, request):
        breadcrumbs = [
            {'title': 'PLS', 'url': reverse('pls:index')},
            {'title': 'My Supplements', 'url': reverse('pls:my_supplements')},
        ]

        supplements = [i for i in request.user.pl_supplements.all()]

        context = {
            'breadcrumbs': breadcrumbs,
            'supplements': create_rows(supplements, 4),
        }
        return render(request, "supplements/userproduct.html", context)


class MyLabels(LoginRequiredMixin, ListView, PagingMixin):
    paginate_by = 20
    ordering = '-updated_at'
    template_name = 'supplements/labels.html'
    model = UserSupplementLabel

    def get_breadcrumbs(self):
        return [
            {'title': 'PLS', 'url': reverse('pls:index')},
            {'title': 'My Labels', 'url': reverse('pls:my_labels')},
        ]

    def add_filters(self, queryset):
        queryset = queryset.filter(user_supplement__user=self.request.user)
        queryset = queryset.filter(current_label_of__isnull=False)
        return queryset

    def get_queryset(self):
        queryset = super().get_queryset()
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
            label_count = f"1 label."
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
    def add_filters(self, queryset):
        return queryset

    def get_breadcrumbs(self):
        return [
            {'title': 'PLS', 'url': reverse('pls:index')},
            {'title': 'All Labels', 'url': reverse('pls:all_labels')},
        ]


def upload_supplement_object_to_aws(user_supplement, obj, name):
    # Randomize filename in order to not overwrite an existing file
    path = f'uploads/u{user_supplement.user.id}/pls_label/{user_supplement.id}'
    return upload_object_to_aws(path, name, obj)


class Label(LabelMixin, LoginRequiredMixin, View, SendToStoreMixin):
    def get_breadcrumbs(self):
        user_supplement = self.label.user_supplement
        user_supplement_url = reverse(
            'pls:user_supplement',
            kwargs={'supplement_id': user_supplement.id}
        )

        return [
            {'title': 'PLS', 'url': reverse('pls:index')},
            {'title': user_supplement.title, 'url': user_supplement_url},
            {'title': 'Label', 'url': self.request.path},
        ]

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
        barcode_obj.scale(0.5, 1)
        barcode_obj.x = barcode_obj.y = 1

        page_merge.render()

        label_pdf = BytesIO()
        PdfWriter().write(label_pdf, base_label_pdf)

        label_pdf.seek(0)

        label.url = upload_supplement_object_to_aws(
            label.user_supplement,
            label_pdf,
            'label.pdf',
        )

    def get(self, request, label_id):
        self.label = label = get_object_or_404(UserSupplementLabel, id=label_id)
        comments = label.comments

        api_data = self.get_api_data(label.user_supplement)
        store_type_and_data = self.get_store_data(request.user)
        context = dict(
            label=label,
            comments=comments.all().order_by('-created_at'),
            breadcrumbs=self.get_breadcrumbs(),
            form=CommentForm(),
            api_data=api_data,
            store_data=store_type_and_data['store_data'],
            store_types=store_type_and_data['store_types'],
        )

        return render(request, "supplements/label_detail.html", context)

    def post(self, request, label_id):
        self.label = label = get_object_or_404(UserSupplementLabel, id=label_id)

        comments = label.comments

        user = request.user
        user_name = user.get_full_name()

        kwargs = {'label_id': label_id}
        reverse_url = reverse('pls:label_detail', kwargs=kwargs)

        action = request.POST['action']
        form = CommentForm()

        def create_comment(text, new_status=''):
            tags = bleach.sanitizer.ALLOWED_TAGS + [
                'span',
                'p',
            ]
            attributes = bleach.sanitizer.ALLOWED_ATTRIBUTES
            attributes.update({'span': ['class']})
            text = bleach.clean(text, tags=tags, attributes=attributes)
            comment = comments.create(user=user,
                                      text=text,
                                      new_status=new_status)
            send_email_against_comment(comment)
            return comment

        if action == 'comment':
            form = CommentForm(request.POST, request.FILES)
            if form.is_valid():
                comment = form.cleaned_data['comment']
                create_comment(comment)
                upload = request.FILES.get('upload')
                if upload:
                    user_supplement = label.user_supplement
                    self.save_label(user, upload, user_supplement)
                    kwargs = {'label_id': user_supplement.current_label.id}
                    reverse_url = reverse('pls:label_detail', kwargs=kwargs)

                return redirect(reverse_url)

        elif action in (label.APPROVED, label.REJECTED):
            label.status = action
            label.save()

            label_class = 'label-danger'
            if action == label.APPROVED:
                label_class = 'label-primary'
                label.generate_sku()
                self.add_barcode_to_label(label)
                label.save()

            comment = (f"<strong>{user_name}</strong> set the status to "
                       f"<span class='label {label_class}'>"
                       f"{label.status_string}</span>.")
            create_comment(comment, new_status=action)
            return redirect(reverse_url)

        context = dict(
            label=label,
            comments=comments.all(),
            breadcrumbs=self.get_breadcrumbs(),
            form=form,
        )

        return render(request, "supplements/label_detail.html", context)


class OrdersShippedWebHook(common_views.OrdersShippedWebHookView):
    store_model = ShopifyStore
    log_model = ShopifyOrderLog
    order_model = PLSOrder
    order_line_model = PLSOrderLine


class Order(common_views.OrderView):
    model = PLSOrder
    paginate_by = 20
    ordering = '-created_at'
    filter_form = OrderFilterForm
    namespace = 'pls'

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


class MyOrders(Order):
    template_name = 'supplements/user_order_list.html'

    def get_breadcrumbs(self):
        return [
            {'title': 'PLS', 'url': reverse('pls:index')},
            {'title': 'My Payments', 'url': reverse('pls:my_orders')},
        ]

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(user=self.request.user)

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


class PayoutView(common_views.PayoutView):
    model = Payout
    paginate_by = 20
    ordering = '-created_at'
    filter_form = PayoutFilterForm
    namespace = 'pls'
    add_form = PayoutForm
    order_class = PLSOrder

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

    def get_breadcrumbs(self):
        return [
            {'title': 'PLS', 'url': reverse('pls:index')},
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
    def get(self, request):
        data_list = []
        for supplement in PLSupplement.objects.all():
            data_list.append(supplement.to_dict())

        data = json.dumps(data_list, indent=2)
        response = HttpResponse(data, content_type='application/json')
        response['Content-Disposition'] = 'attachment; filename="supplements.json"'
        return response
