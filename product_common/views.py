from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.views import View
from django.views.generic.list import ListView

import requests
import simplejson as json
from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.models import ShopifyStore
from leadgalaxy.utils import order_track_fulfillment
from shopify_orders.models import ShopifyOrderLog

from .forms import OrderFilterForm, PayoutFilterForm, ProductEditForm, ProductForm
from .lib.shipstation import get_shipstation_shipments
from .lib.views import BaseMixin, PagingMixin, SendToStoreMixin, upload_image_to_aws
from .models import Order, OrderLine, Payout, Product


class IndexView(LoginRequiredMixin, ListView, BaseMixin, PagingMixin):
    model = Product
    paginate_by = 20
    ordering = '-created_at'

    def get_template(self):
        return 'product_common/index.html'

    def get_template_names(self):
        return [self.get_template()]

    def get_new_product_url(self):
        assert self.namespace, "Either give namespace or override"
        return reverse(f'{self.namespace}:product_add')

    def get_breadcrumbs(self):
        return [
            {'title': 'PLS', 'url': reverse('index')},
            {'title': 'Products', 'url': reverse(f'{self.namespace}:index')},
        ]

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        self.add_paging_context(context)

        context.update({
            'breadcrumbs': self.get_breadcrumbs(),
            'products': context['object_list'],
            'add_new_product_url': self.get_new_product_url(),
        })
        return context


class ProductAddView(LoginRequiredMixin, View, BaseMixin):
    form = ProductForm
    model = Product
    template_name = 'product_common/add_product.html'

    def get_template(self):
        return self.template_name

    def get_redirect_url(self):
        assert self.namespace, "Either give namespace or override"
        return reverse(f'{self.namespace}:index')

    def get_breadcrumbs(self):
        return [
            {'title': 'PLS', 'url': reverse('index')},
        ]

    def process_valid_form(self, form):
        request = self.request
        user_id = request.user.id

        product_image = request.FILES['product_image']
        product_image_url = upload_image_to_aws(product_image,
                                                'pls_image',
                                                user_id)

        product = self.model.objects.create(
            title=form.cleaned_data['title'],
            description=form.cleaned_data['description'],
            category=form.cleaned_data['category'],
            tags=form.cleaned_data['tags'],
            shipstation_sku=form.cleaned_data['shipstation_sku'],
            cost_price=form.cleaned_data['cost_price'],
        )

        product.images.create(
            product=product,
            position=0,
            image_url=product_image_url,
        )

    def get(self, request):
        context = {
            'breadcrumbs': self.get_breadcrumbs(),
            'form': self.form(),
        }
        return render(request, self.get_template(), context)

    def post(self, request):
        form = self.form(request.POST, request.FILES)
        if form.is_valid():
            self.process_valid_form(form)
            return redirect(self.get_redirect_url())

        context = {
            'breadcrumbs': self.get_breadcrumbs(),
            'form': form,
        }
        return render(request, self.get_template(), context)


class ProductDetailView(LoginRequiredMixin, View, BaseMixin, SendToStoreMixin):
    form = ProductEditForm

    def get_breadcrumbs(self, product_id):
        breadcrumbs = [
            {'title': 'PLS', 'url': reverse('index')},
            {'title': 'Product', 'url': reverse(f'{self.namespace}:index')},
            {'title': 'Product Detail',
             'url': reverse(f'{self.namespace}:product_detail',
                            kwargs={'product_id': product_id})},
        ]
        return breadcrumbs

    def get_product(self, user, product_id):
        return get_object_or_404(Product, id=product_id)

    def get_product_data(self, user, product_id):
        product = self.get_product(user, product_id)

        form_data = product.to_dict()

        api_data = self.get_api_data(product)
        store_type_and_data = self.get_store_data(user)

        data = dict(
            form_data=form_data,
            api_data=api_data,
            image_urls=form_data.pop('image_urls'),
            store_data=store_type_and_data['store_data'],
            store_types=store_type_and_data['store_types'],
        )

        return data

    def get_template(self):
        return 'product_common/product.html'

    def get(self, request, product_id):
        data = self.get_product_data(request.user, product_id)

        context = {
            'breadcrumbs': self.get_breadcrumbs(product_id),
            'form': self.form(initial=data['form_data']),
            'api_data': data['api_data'],
            'image_urls': data['image_urls'],
            'store_data': data['store_data'],
            'store_types': data['store_types'],
        }
        return render(request, self.get_template(), context)

    def post(self, request, product_id):
        product = get_object_or_404(Product, id=product_id)

        form = self.form(request.POST, request.FILES)
        if form.is_valid():
            user_id = request.user.id

            product.title = form.cleaned_data['title']
            product.description = form.cleaned_data['description']
            product.category = form.cleaned_data['category']
            product.tags = form.cleaned_data['tags']
            product.shipstation_sku = form.cleaned_data['shipstation_sku']
            product.cost_price = form.cleaned_data['cost_price']
            product.save()

            product_image = request.FILES.get('product_image')
            if product_image:
                product_image_url = upload_image_to_aws(product_image,
                                                        'pls_image',
                                                        user_id)

                product.images.create(
                    product=product,
                    position=1,
                    image_url=product_image_url,
                )

            url = reverse(f'{self.namespace}:product_detail',
                          kwargs={'product_id': product.id})
            return redirect(url)

        data = self.get_product_data(request.user, product_id)
        context = {
            'breadcrumbs': self.get_breadcrumbs(product_id),
            'form': form,
            'image_urls': data['image_urls'],
            'store_data': data['store_data'],
            'store_types': data['store_types'],
        }
        return render(request, self.get_template(), context)


class OrdersShippedWebHookView(View, BaseMixin):
    store_model = ShopifyStore
    log_model = ShopifyOrderLog
    order_model = Order
    order_line_model = OrderLine

    def fulfill_shopify_order(self, data):
        store = self.store_model.objects.get(id=data['store_id'])
        order_id = data['order_id']
        line_id = int(data['line_id'])
        tracking_number = data['tracking_number']
        location_id = store.get_primary_location()
        notify_customer = True
        aftership_domain = 'track'

        api_data = order_track_fulfillment(**{
            'store_id': store.id,
            'line_id': line_id,
            'order_id': order_id,
            'source_tracking': tracking_number,
            'use_usps': data.get('is_usps') == 'usps',
            'location_id': location_id,
            'user_config': {
                'send_shipping_confirmation': notify_customer,
                'validate_tracking_number': False,
                'aftership_domain': aftership_domain,
            }
        })

        url = store.api('orders', order_id, 'fulfillments')
        rep = requests.post(url=url, json=api_data)

        try:
            rep.raise_for_status()

            self.log_model.objects.update_order_log(
                store=store,
                user=self.request.user,
                log='Manually Fulfilled in Shopify',
                order_id=order_id,
                line_id=line_id,
            )

        except:
            if 'already fulfilled' not in rep.text and \
               'please try again' not in rep.text and \
               'Internal Server Error' not in rep.text:
                raven_client.captureException(
                    level='warning',
                    extra={'response': rep.text})

            raise

    def fulfill_order(self, shipment):
        try:
            order_key = shipment['orderKey']
        except KeyError:
            return

        try:
            order = self.order_model.objects.get(shipstation_key=order_key)
        except self.order_model.DoesNotExist:
            return

        store_type = order.store_type
        store_id = order.store_id
        store_order_id = order.store_order_id
        tracking_number = shipment['trackingNumber']

        get_line = self.order_line_model.objects.get

        with transaction.atomic():
            order.batch_number = shipment['batchNumber']
            order.is_fulfilled = True
            order.save()

            for item in shipment.get('shipmentItems', []):
                try:
                    line = get_line(shipstation_key=item['lineItemKey'])
                except self.order_line_model.DoesNotExist:
                    continue

                data = {
                    'store_id': store_id,
                    'order_id': store_order_id,
                    'line_id': line.line_id,
                    'tracking_number': tracking_number,
                }
                if store_type == self.order_model.SHOPIFY:
                    self.fulfill_shopify_order(data)

    def get_shipments(self):
        data = json.loads(self.request.body.decode())
        if data['resource_type'] != 'SHIP_NOTIFY':
            # Process when the whole order is shipped, return otherwise.
            return

        resource_url = data['resource_url']
        resource_url = resource_url.replace("False", "True")

        shipments = get_shipstation_shipments(resource_url)
        for shipment in shipments:
            yield shipment

    def post(self, request, *args, **kwargs):
        for shipment in self.get_shipments():
            self.fulfill_order(shipment)

        return HttpResponse('OK')


class OrderView(LoginRequiredMixin, ListView, BaseMixin, PagingMixin):
    model = Order
    paginate_by = 20
    ordering = '-created_at'
    filter_form = OrderFilterForm

    def get_queryset(self):
        queryset = super().get_queryset()

        form = self.form = self.filter_form(self.request.GET)
        if form.is_valid():
            order_number = form.cleaned_data['order_number']
            if order_number:
                queryset = queryset.filter(order_number=order_number)

            status = form.cleaned_data['status']
            if status:
                queryset = queryset.filter(status=status)

            email = form.cleaned_data['email']
            if email:
                queryset = queryset.filter(user__email=email)

            amount = form.cleaned_data['amount']
            if amount:
                queryset = queryset.filter(amount=amount * 100)

            created_at = form.cleaned_data['date']
            if created_at:
                queryset = queryset.filter(created_at__date=created_at)

        return queryset

    def get_breadcrumbs(self):
        return [
            {'title': 'PLS', 'url': reverse('pls:index')},
            {'title': 'Orders', 'url': reverse(f'{self.namespace}:order_list')},
        ]

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['form'] = self.form
        context['breadcrumbs'] = self.get_breadcrumbs()
        self.add_paging_context(context)
        return context


class PayoutView(LoginRequiredMixin, ListView, BaseMixin, PagingMixin):
    model = Payout
    paginate_by = 20
    ordering = '-created_at'
    filter_form = PayoutFilterForm

    def get_breadcrumbs(self):
        return [
            {'title': 'PLS', 'url': reverse('pls:index')},
            {'title': 'Payouts', 'url': reverse(f'{self.namespace}:payout_list')},
        ]

    def get_queryset(self):
        queryset = super().get_queryset()

        form = self.form = self.filter_form(self.request.GET)
        if form.is_valid():
            order_number = form.cleaned_data['order_number']
            if order_number:
                queryset = queryset.filter(
                    payout_items__order_number=order_number
                ).distinct()

            status = form.cleaned_data['status']
            if status:
                queryset = queryset.filter(status=status)

            email = form.cleaned_data['email']
            if email:
                queryset = queryset.filter(
                    payout_items__user__email=email,
                ).distinct()

            reference_number = form.cleaned_data['refnum']
            if reference_number:
                queryset = queryset.filter(
                    reference_number=reference_number
                )

            amount = form.cleaned_data['amount']
            if amount:
                queryset = queryset.filter(amount=amount * 100)

            created_at = form.cleaned_data['date']
            if created_at:
                queryset = queryset.filter(created_at__date=created_at)

        return queryset

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['form'] = self.form
        context['breadcrumbs'] = self.get_breadcrumbs()
        self.add_paging_context(context)
        return context


class OrderItemListView(LoginRequiredMixin, ListView, PagingMixin):
    model = None
    paginate_by = 20
    ordering = '-created_at'
    filter_form = None

    def get_queryset(self):
        queryset = super().get_queryset()

        form = self.form = self.filter_form(self.request.GET)
        if form.is_valid():
            order_number = form.cleaned_data['order_number']
            if order_number:
                queryset = queryset.filter(pls_order__order_number=order_number)

            status = form.cleaned_data['status']
            if status:
                queryset = queryset.filter(status=status)

            email = form.cleaned_data['email']
            if email:
                queryset = queryset.filter(pls_order__user__email=email)

            reference_number = form.cleaned_data['refnum']
            if reference_number:
                queryset = queryset.filter(
                    payout__reference_number=reference_number
                )

            label_sku = form.cleaned_data['label_sku']
            if label_sku:
                queryset = queryset.filter(
                    label__sku=label_sku
                )

            created_at = form.cleaned_data['date']
            if created_at:
                queryset = queryset.filter(created_at__date=created_at)

            line_status = form.cleaned_data['line_status']
            if line_status:
                if line_status == 'printed':
                    queryset = queryset.filter(is_label_printed=True)
                elif line_status == 'not-printed':
                    queryset = queryset.filter(is_label_printed=False)

            product_sku = form.cleaned_data['product_sku']
            if product_sku:
                queryset = queryset.filter(
                    label__user_supplement__pl_supplement__shipstation_sku=product_sku
                )

            label_size = form.cleaned_data['label_size']
            if label_size:
                queryset = queryset.filter(
                    label__user_supplement__pl_supplement__label_size=label_size
                )

            batch_number = form.cleaned_data['batch_number']
            if batch_number:
                queryset = queryset.filter(pls_order__batch_number=batch_number)

            shipstation_status = form.cleaned_data['shipstation_status']
            if shipstation_status:
                if shipstation_status == 'fulfilled':
                    queryset = queryset.filter(pls_order__is_fulfilled=True)
                elif shipstation_status == 'unfulfilled':
                    queryset = queryset.filter(pls_order__is_fulfilled=False)

        return queryset

    def get_breadcrumbs(self):
        return [
            {'title': 'PLS', 'url': reverse('pls:index')},
            {'title': 'Order Items', 'url': reverse(f'{self.namespace}:orderitem_list')},
        ]

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['form'] = self.form
        context['breadcrumbs'] = self.get_breadcrumbs()
        self.add_paging_context(context)
        return context
