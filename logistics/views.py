import decimal

import requests
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from shopified_core.shipping_helper import get_counrties_list, country_from_code
from shopified_core.paginators import SimplePaginator
from .models import Product, Warehouse, Carrier, Order, Listing, Supplier, Variant
from .forms import WarehouseForm
from .utils import get_carrier_types


class ProductsListView(LoginRequiredMixin, ListView):
    model = Product
    template_name = 'logistics/products.html'
    paginator_class = SimplePaginator
    context_object_name = 'products'

    def get_queryset(self):
        products = super().get_queryset()
        products = products.filter(user=self.request.user.models_user)

        title = self.request.GET.get('title')
        if title:
            products = products.filter(title__icontains=title)

        sort = self.request.GET.get('sort', 'title')
        return products.order_by(sort)

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['breadcrumbs'] = ['Logistics', 'Products']
        return ctx


class ProductView(LoginRequiredMixin, View):
    model = Product
    template_name = 'logistics/product.html'

    def get_context_data(self, product=None, **kwargs):
        ctx = {}
        ctx['breadcrumbs'] = ['Logistics', {'title': 'Products', 'url': reverse('logistics:products')}, 'Product']

        models_user = self.request.user.models_user
        warehouses = Warehouse.objects.active().filter(user=models_user)
        ctx['warehouses'] = warehouses
        ctx['warehouses_data'] = [w.to_dict() for w in Warehouse.objects.active().filter(user=models_user)]

        if product is None:
            return ctx

        ctx['product'] = product
        ctx['variants_data'] = [v.to_dict() for v in ctx['product'].variants.all()]
        ctx['inventories'] = {}
        ctx['prices'] = {}
        for listing in Listing.objects.select_related('supplier').filter(supplier__warehouse__user=models_user,
                                                                         supplier__product=ctx['product']):
            key = f"{listing.supplier.warehouse_id}_{listing.variant_id}"
            ctx['inventories'][key] = listing.inventory
            ctx['prices'][key] = listing.price

        ctx['listings_data'] = []
        for warehouse in warehouses:
            listing = {'full_name': warehouse.get_full_name(), 'variants': []}
            for variant in product.variants.all():
                listing_key = f"{warehouse.id}_{variant.id}"
                listing['variants'].append({
                    'listing_key': listing_key,
                    'inventory': ctx['inventories'].get(listing_key, ''),
                    'price': ctx['prices'].get(listing_key, ''),
                })
            ctx['listings_data'].append(listing)

        return ctx

    def get(self, request, pk=None, supplier_id=None):
        context = {}
        if pk is not None:
            context['product'] = get_object_or_404(Product, pk=pk, user=request.user.models_user)
        elif supplier_id is not None:
            context['product'] = get_object_or_404(Product, suppliers__id=supplier_id, user=request.user.models_user)

        if request.is_ajax():
            if supplier_id:
                supplier = get_object_or_404(Supplier, id=supplier_id, product__user=request.user.models_user)
                return JsonResponse(supplier.variants_connection, safe=False)
            return JsonResponse(context['product'].variants_connection, safe=False)

        return render(request, self.template_name, self.get_context_data(**context))

    def post(self, request, pk=None, supplier_id=None):
        if request.is_ajax():
            return HttpResponse(status_code=405)

        models_user = request.user.models_user
        if pk is not None:
            product = get_object_or_404(Product, pk=pk, user=models_user)
        elif supplier_id is not None:
            product = get_object_or_404(Product, suppliers__id=supplier_id, user=models_user)
        else:
            product = Product(user=models_user)
        product.title = request.POST.get('title')
        product.hs_tariff = request.POST.get('hs_tariff')
        product.variants_map = request.POST['variants_map'] or '[]'
        product.save()

        deleted_variants = []
        variant_ids = request.POST.getlist('variant_ids')
        for variant_id in variant_ids:
            variant_id = int(variant_id)
            title = request.POST.get(f'variant_title_{variant_id}')
            sku = request.POST.get(f'variant_sku_{variant_id}')
            if not title and not sku:
                if variant_id > 0:
                    Variant.objects.filter(id=variant_id, product=product).delete()
                    deleted_variants.append(variant_id)
                continue

            Variant(product=product, title=title, sku=sku,
                    id=variant_id if variant_id > 0 else None,
                    weight=request.POST.get(f'variant_weight_{variant_id}') or 0,
                    length=request.POST.get(f'variant_length_{variant_id}') or 0,
                    width=request.POST.get(f'variant_width_{variant_id}') or 0,
                    height=request.POST.get(f'variant_height_{variant_id}') or 0).save()

        listings = request.POST.getlist('listings')
        for listing in listings:
            warehouse_id, variant_id = listing.split('_')
            if int(variant_id) in deleted_variants:
                continue

            inventory = request.POST.get(f'inventory_{listing}') or None
            price = decimal.Decimal(request.POST.get(f'price_{listing}') or 0)

            supplier, created = Supplier.objects.get_or_create(warehouse_id=int(warehouse_id), product=product)
            if not inventory and not price:
                Listing.objects.filter(supplier=supplier, variant_id=int(variant_id)).delete()
                if not supplier.listings.exists:
                    supplier.delete()
            else:
                Listing.objects.update_or_create(supplier=supplier,
                                                 variant_id=int(variant_id),
                                                 defaults={'inventory': inventory, 'price': price})

        link = reverse("logistics:product", kwargs={'pk': product.id})
        messages.success(request, f'Product <a href="{link}">"{product.title}"</a> saved successfully.')
        if pk is not None or supplier_id is not None:
            return redirect('logistics:products')
        else:
            return redirect('logistics:product', pk=product.id)


class WarehousesListView(LoginRequiredMixin, ListView):
    model = Warehouse
    template_name = 'logistics/warehouses.html'
    paginator_class = SimplePaginator
    context_object_name = 'warehouses'

    def get_queryset(self):
        warehouses = super().get_queryset()
        warehouses = warehouses.filter(user=self.request.user.models_user, deleted_at__isnull=True)

        search_field = self.request.GET.get('search')
        if search_field:
            warehouses = warehouses.filter(
                models.Q(name__icontains=search_field)
                | models.Q(company__icontains=search_field)
                | models.Q(address1__icontains=search_field)
                | models.Q(city__icontains=search_field)
                | models.Q(province__icontains=search_field)
                | models.Q(zip__icontains=search_field)
                | models.Q(country__icontains=search_field)
            )

        sorting = self.request.GET.get('sorting', 'name')
        return warehouses.order_by(sorting)

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['breadcrumbs'] = ['Logistics', 'Warehouses']
        ctx['countries'] = get_counrties_list()
        return ctx

    def post(self, request):
        data = request.POST.copy()
        data['country'] = country_from_code(data['country_code'])
        data['user'] = request.user.models_user.id
        form = WarehouseForm(data)
        if form.is_valid():
            warehouse = form.save()
            warehouse.source_address()

        return JsonResponse({'errors': form.errors})


class CarriersListView(LoginRequiredMixin, ListView):
    model = Carrier
    template_name = 'logistics/carriers.html'
    paginator_class = SimplePaginator
    context_object_name = 'carriers'

    def get_queryset(self):
        carriers = super().get_queryset()
        carriers = carriers.filter(account__user=self.request.user.models_user)

        search_field = self.request.GET.get('search')
        if search_field:
            carriers = carriers.filter(
                models.Q(description__icontains=search_field)
                | models.Q(carrier_type__name__icontains=search_field)
                | models.Q(carrier_type__label__icontains=search_field)
                | models.Q(reference__icontains=search_field)
            )

        sorting = self.request.GET.get('sorting', 'description')
        return carriers.order_by(sorting)

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['breadcrumbs'] = ['Logistics', 'Carriers']
        ctx['carrier_types'] = get_carrier_types()
        return ctx


class OrdersListView(LoginRequiredMixin, ListView):
    model = Order
    template_name = 'logistics/orders.html'
    paginator_class = SimplePaginator
    context_object_name = 'orders'

    def get_queryset(self):
        orders = super().get_queryset()
        orders = orders.filter(warehouse__user=self.request.user.models_user)

        order_id = self.kwargs.get('order_id')
        if order_id:
            return orders.filter(id=int(order_id))

        orders = orders.filter(is_paid=True)
        search_field = self.request.GET.get('search')
        if search_field:
            orders = orders.filter(
                models.Q(warehouse__name__icontains=search_field)
                | models.Q(tracking_number__icontains=search_field)
                | models.Q(store_type__icontains=search_field)
                | models.Q(store_order_number__icontains=search_field)
            )

        sorting = self.request.GET.get('sorting', 'warehouse__name')
        return orders.order_by(sorting)

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['breadcrumbs'] = ['Logistics', 'Orders']
        ctx['carrier_types'] = get_carrier_types()
        return ctx


def label(request, order_id):
    order = get_object_or_404(Order, id=order_id, warehouse__user=request.user.models_user, source_label_url__startswith='http')
    response = requests.get(order.source_label_url, stream=True)
    response.raw.decode_content = True
    response = HttpResponse(content_type='image/png', content=response.raw)
    return response
