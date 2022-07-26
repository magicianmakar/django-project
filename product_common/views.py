import arrow

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q, F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils import timezone
from django.views import View
from django.views.generic.list import ListView

import simplejson as json
from leadgalaxy.models import UserProfile
from shopified_core.utils import safe_int

from .forms import OrderFilterForm, PayoutFilterForm, ProductEditForm, ProductForm
from .lib.shipstation import get_shipstation_orders, get_shipstation_shipments
from .lib.views import BaseMixin, PagingMixin, SendToStoreMixin, upload_image_to_aws
from .models import Order, OrderLine, Payout, Product
from django.core.cache import cache


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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
            'form': self.form(user=request.user),
        }
        return render(request, self.get_template(), context)

    def post(self, request):
        form = self.form(request.POST, request.FILES, user=request.user)
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
    order_model = Order
    order_line_model = OrderLine

    def fulfill_order(self, shipment):
        with transaction.atomic():
            items = shipment.get('shipmentItems', [])
            self.order_model.objects.filter(order_items__shipstation_key__in=[i['lineItemKey'] for i in items]).update(
                status=self.order_model.SHIPPED if shipment['trackingNumber'] else F('status'),
                batch_number=shipment['batchNumber'],
                is_fulfilled=True,
            )

            for item in items:
                try:
                    line = self.order_line_model.objects.get(shipstation_key=item['lineItemKey'])
                    line.tracking_number = shipment['trackingNumber']
                    line.save_order_track()

                except self.order_line_model.DoesNotExist:
                    continue

    def get_shipments(self):
        data = json.loads(self.request.body.decode())
        if data['resource_type'] != 'SHIP_NOTIFY':
            # Process when the whole order is shipped, return otherwise.
            return

        resource_url = data['resource_url']
        resource_url = resource_url.replace("False", "True")
        # Search for order number with hash is being treated as a fragment identifier
        resource_url = resource_url.replace('#', '%23')  # Encoded char

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
                try:
                    order_number, order_id = order_number.split('-')
                except ValueError:
                    order_id = safe_int(order_number)
                finally:
                    query_search = Q(order_number__endswith=order_number)
                    if order_id:
                        query_search |= Q(id=order_id)
                    queryset = queryset.filter(query_search)

            status = form.cleaned_data['status']
            if status:
                queryset = queryset.filter(status=status)

            email = form.cleaned_data['email']
            if email:
                queryset = queryset.filter(user__email=email)

            reference_number = form.cleaned_data['refnum']
            if reference_number:
                queryset = queryset.filter(
                    Q(order_items__line_payout__reference_number=reference_number)
                    | Q(order_items__shipping_payout__reference_number=reference_number)
                )

            amount = form.cleaned_data['amount']
            if amount:
                queryset = queryset.filter(amount=amount * 100)

            transaction_id = form.cleaned_data['transaction_id']
            if transaction_id:
                queryset = queryset.filter(
                    Q(stripe_transaction_id=transaction_id)
                    | Q(id=safe_int(transaction_id))
                )

            supplier = form.cleaned_data['supplier']
            if supplier:
                queryset = queryset.filter(
                    order_items__label__user_supplement__pl_supplement__supplier_id=supplier
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

    def get_breadcrumbs(self):
        return [
            {'title': 'PLS', 'url': reverse('pls:index')},
            {'title': 'Orders', 'url': reverse(f'{self.namespace}:order_list')},
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'form': self.form,
            'breadcrumbs': self.get_breadcrumbs(),
            'date_range': self.request.GET.get('date', None),
        })
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
                    payout_lines__pls_order__order_number=order_number
                ).distinct()

            status = form.cleaned_data['status']
            if status:
                queryset = queryset.filter(status=status)

            email = form.cleaned_data['email']
            if email:
                queryset = queryset.filter(
                    payout_lines__pls_order__user__email=email,
                ).distinct()

            reference_number = form.cleaned_data['refnum']
            if reference_number:
                queryset = queryset.filter(
                    reference_number=reference_number
                )

            amount = form.cleaned_data['amount']
            if amount:
                queryset = queryset.filter(amount=amount * 100)

            supplier = form.cleaned_data['supplier']
            if supplier:
                queryset = queryset.filter(supplier_id=supplier)

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'form': self.form,
            'breadcrumbs': self.get_breadcrumbs(),
            'date_range': self.request.GET.get('date', None),
        })
        self.add_paging_context(context)
        return context


class OrderItemListView(LoginRequiredMixin, ListView, PagingMixin):
    model = None
    paginate_by = 20
    ordering = '-created_at'
    filter_form = None
    cancelled_orders_cache = {}

    def get_queryset(self):
        queryset = super().get_queryset()

        form = self.form = self.filter_form(self.request.GET)
        if form.is_valid():
            order_number = form.cleaned_data['order_number']
            if order_number:
                try:
                    order_number, order_id = order_number.split('-')
                except ValueError:
                    query_search = Q(pls_order__order_number__endswith=order_number)
                    order_id = safe_int(order_number)
                    if order_id:
                        query_search |= Q(pls_order_id=order_id)
                    queryset = queryset.filter(query_search)
                else:
                    queryset = queryset.filter(pls_order__order_number__endswith=order_number, pls_order_id=order_id)

            warehouse_account = UserProfile.objects.get(user=self.request.user.models_user.id).warehouse_account
            if warehouse_account:
                queryset = queryset.filter(
                    label__user_supplement__pl_supplement__shipstation_account=UserProfile.objects.get(
                        user=self.request.user.models_user.id).warehouse_account)
            status = form.cleaned_data['status']
            if status:
                queryset = queryset.filter(status=status)

            email = form.cleaned_data['email']
            if email:
                queryset = queryset.filter(pls_order__user__email__icontains=email)

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

            line_status = form.cleaned_data['line_status']
            if line_status:
                if line_status == 'printed':
                    queryset = queryset.filter(is_label_printed=True)
                elif line_status == 'not-printed':
                    queryset = queryset.filter(is_label_printed=False)

            product_sku = form.cleaned_data['product_sku']
            if product_sku:
                queryset = queryset.filter(
                    label__user_supplement__pl_supplement__shipstation_sku__in=product_sku
                )

            label_size = form.cleaned_data['label_size']
            if label_size:
                queryset = queryset.filter(
                    label__user_supplement__pl_supplement__label_size__in=label_size
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

            cancelled = form.cleaned_data['cancelled']
            if cancelled:
                cancelled_order_ids = self.get_cancelled_order_ids()
                for id, number in cancelled_order_ids.items():
                    if id.isnumeric():
                        queryset = queryset.exclude(pls_order_id=id, pls_order__order_number=number)

            supplier = form.cleaned_data['supplier']
            if supplier:
                queryset = queryset.filter(
                    label__user_supplement__pl_supplement__supplier_id=supplier
                )
            elif self.request.user.can('pls_supplier.use') and self.request.user.profile.supplier is not None:
                queryset = queryset.filter(label__user_supplement__pl_supplement__supplier_id=self.request.user.profile.supplier)

            date = self.request.GET.get('date', None)
            self.paginate_by = self.request.GET.get('paginate_by', 20)
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

    def get_breadcrumbs(self):
        return [
            {'title': 'PLS', 'url': reverse('pls:index')},
            {'title': 'Order Items', 'url': reverse(f'{self.namespace}:orderitem_list')},
        ]

    def get_cancelled_order_ids(self):
        cache_key = 'shipstation_cancelled_orders'
        try:
            cached_order_data = cache.get(cache_key).get('data', False)
        except:
            cached_order_data = False
        if not cached_order_data:
            params = {'orderStatus': 'cancelled'}
            orders = get_shipstation_orders(params=params)
            for order in orders:
                try:
                    number, id = order['orderNumber'].split('-')
                except ValueError:
                    continue
                else:
                    self.cancelled_orders_cache[id] = number
            cache.set(cache_key, {'executed_date': str(timezone.now()), 'data': self.cancelled_orders_cache},
                      timeout=86400 * 3)  # "hard" refresh 3 days
        else:
            if not self.cancelled_orders_cache:
                self.cancelled_orders_cache = cache.get(cache_key)['data']

                # fetch lastly modified orders and add them into local cache
                params = {'orderStatus': 'cancelled', 'modifyDateStart': cache.get(cache_key)['executed_date']}
                orders = get_shipstation_orders(params=params)
                for order in orders:
                    try:
                        number, id = order['orderNumber'].split('-')
                    except ValueError:
                        continue
                    else:
                        self.cancelled_orders_cache[id] = number
                cache.set(cache_key, {'executed_date': str(timezone.now()), 'data': self.cancelled_orders_cache},
                          timeout=600)  # refresh cache with latest updated orders

        return self.cancelled_orders_cache

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        count = sum(self.get_queryset().values_list('quantity', flat=True))
        context.update({
            'form': self.form,
            'breadcrumbs': self.get_breadcrumbs(),
            'total_line_items': count,
            'date_range': self.request.GET.get('date', None),
            'warehouse_account': UserProfile.objects.get(user=self.request.user.models_user.id).warehouse_account
        })
        self.add_paging_context(context)
        return context
