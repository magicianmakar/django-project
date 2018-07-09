import simplejson as json

from django.http import Http404
from django.contrib.auth.models import User
from django.utils import timezone

from rest_framework import viewsets, mixins
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_hooks.models import Hook

from shopified_core import permissions
from shopified_core.utils import safeFloat, safeInt

from leadgalaxy.models import ShopifyProduct, ShopifyStore
import leadgalaxy.tasks
import leadgalaxy.utils

from commercehq_core.models import CommerceHQProduct, CommerceHQStore
import commercehq_core.tasks
import commercehq_core.utils

from product_alerts.models import ProductChange

from .serializers import *


class HookViewSet(viewsets.ModelViewSet):
    queryset = Hook.objects.all()
    serializer_class = HookSerializer

    def get_queryset(self):
        return Hook.objects.filter(user=self.request.user)

    def pre_save(self, obj):
        obj.user = self.request.user


class ShopifyProductViewSet(mixins.RetrieveModelMixin,
                            mixins.UpdateModelMixin,
                            mixins.ListModelMixin,
                            viewsets.GenericViewSet):
    model = ShopifyProduct
    serializer_class = ShopifyProductSerializer

    def get_queryset(self):
        queryset = ShopifyProduct.objects.filter(user=self.request.user)
        if self.request.GET.get('store_id'):
            queryset = queryset.filter(store_id=self.request.GET.get('store_id'))
        if self.request.GET.get('title'):
            queryset = queryset.filter(title=self.request.GET.get('title'))
        return queryset


class CommerceHQProductViewSet(mixins.RetrieveModelMixin,
                               mixins.UpdateModelMixin,
                               mixins.ListModelMixin,
                               viewsets.GenericViewSet):
    model = CommerceHQProduct
    serializer_class = CommerceHQProductSerializer

    def get_queryset(self):
        queryset = CommerceHQProduct.objects.filter(user=self.request.user)
        if self.request.GET.get('store_id'):
            queryset = queryset.filter(store_id=self.request.GET.get('store_id'))
        if self.request.GET.get('title'):
            queryset = queryset.filter(title=self.request.GET.get('title'))
        return queryset


class ShopifyStoreViewSet(mixins.RetrieveModelMixin,
                          mixins.ListModelMixin,
                          viewsets.GenericViewSet):
    model = ShopifyStore
    serializer_class = ShopifyStoreSerializer

    def get_queryset(self):
        queryset = self.request.user.profile.get_shopify_stores()
        if self.request.GET.get('title'):
            queryset = queryset.filter(title=self.request.GET.get('title'))
        return queryset


class CommerceHQStoreViewSet(mixins.RetrieveModelMixin,
                             mixins.ListModelMixin,
                             viewsets.GenericViewSet):
    model = CommerceHQStore
    serializer_class = CommerceHQStoreSerializer

    def get_queryset(self):
        queryset = self.request.user.profile.get_chq_stores()
        if self.request.GET.get('title'):
            queryset = queryset.filter(title=self.request.GET.get('title'))
        return queryset


class ProductVisibilityUpdate(APIView):
    def post(self, request, pk, store_type):
        user = request.user
        visibility = True if request.DATA.get('visibility', False) else False
        if store_type == 'shopify':
            product = ShopifyProduct.objects.get(id=pk)
            permissions.user_can_edit(user, product)
            leadgalaxy.tasks.update_product_visibility.delay(request.user.id, pk, visibility)
            data = ShopifyProductSerializer(product).data
            data['visibility'] = visibility
            return Response(data)
        elif store_type == 'chq':
            product = CommerceHQProduct.objects.get(id=pk)
            permissions.user_can_edit(user, product)
            commercehq_core.tasks.update_product_visibility.delay(request.user.id, pk, visibility)
            data = CommerceHQProductSerializer(product).data
            data['visibility'] = visibility
            return Response(data)
        raise Http404


class ProductNotesUpdate(APIView):
    def post(self, request, pk, store_type):
        user = request.user
        notes = request.DATA.get('notes')
        if store_type == 'shopify':
            product = ShopifyProduct.objects.get(id=pk)
            permissions.user_can_edit(user, product)
            data = ShopifyProductSerializer(product).data
        elif store_type == 'chq':
            product = CommerceHQProduct.objects.get(id=pk)
            permissions.user_can_edit(user, product)
            data = CommerceHQProductSerializer(product).data
        if product is not None and notes is not None:
            product.notes = notes
            product.save()
            data['notes'] = notes
            return Response(data)
        raise Http404


class ProductVariantList(APIView):
    def get(self, request, pk, store_type):
        user = request.user
        if store_type == 'shopify':
            product = ShopifyProduct.objects.get(id=pk)
        elif store_type == 'chq':
            product = CommerceHQProduct.objects.get(id=pk)

        permissions.user_can_view(user, product)
        variants = []
        if store_type == 'shopify':
            # Get product info from shopify store
            product_data = leadgalaxy.utils.get_shopify_product(product.store, product.shopify_id)
            for variant in product_data.get('variants', []):
                variants.append({
                    'id': variant['id'],
                    'title': variant['title'],
                })
        elif store_type == 'chq':
            # Get product info from chq store
            product_data = product.retrieve()
            for variant in product_data.get('variants', []):
                variants.append({
                    'id': variant['id'],
                    'title': ' / '.join(variant['variant']),
                })
        return Response(variants)


class ProductVariantUpdate(APIView):
    def post(self, request, pk, store_type):
        user = request.user
        variant_id = safeInt(request.DATA.get('variant_id'))
        price = safeFloat(request.DATA.get('price'))
        if store_type == 'shopify':
            product = ShopifyProduct.objects.get(id=pk)
            permissions.user_can_edit(user, product)
            data = ShopifyProductSerializer(product).data
        elif store_type == 'chq':
            product = CommerceHQProduct.objects.get(id=pk)
            permissions.user_can_edit(user, product)
            data = CommerceHQProductSerializer(product).data

        if store_type == 'shopify':
            # Get product info from shopify store
            product_data = leadgalaxy.utils.get_shopify_product(product.store, product.shopify_id)
            for idx, variant in enumerate(product_data.get('variants', [])):
                if variant['id'] == variant_id:
                    product_data['variants'][idx]['price'] = round(price, 2)
                    res = leadgalaxy.utils.update_shopify_product_data(product.store, product.shopify_id, product_data)
                    res.raise_for_status()
                    data['variant_id'] = variant_id
                    return Response(data)
        elif store_type == 'chq':
            # Get product info from chq store
            product_data = product.retrieve()
            for idx, variant in enumerate(product_data.get('variants', [])):
                if variant['id'] == variant_id:
                    product_data['variants'][idx]['price'] = round(price, 2)
                    res = commercehq_core.utils.update_chq_product(product.store, product.source_id, {'variants': product_data['variants']})
                    res.raise_for_status()
                    data['variant_id'] = variant_id
                    return Response(data)
        raise Http404


class ShopifyOrderDetail(APIView):
    def get(self, request, pk):
        user = request.user
        store_id = request.GET.get('store_id')
        ret = {}
        if store_id:
            store = ShopifyStore.objects.get(id=store_id)
            permissions.user_can_view(user, store)
            order_data = leadgalaxy.utils.get_shopify_order(store, pk)
            ret = {
                'order_no': pk,
                'order_label': order_data['order_number'],
                'total_price': order_data['total_price'],
                'financial_status': order_data['financial_status'],
                'fulfillment_status': order_data['fulfillment_status'],
                'currency': order_data['currency'],
            }

        return Response(ret)


class OrderNotesUpdate(APIView):
    def post(self, request, pk, store_type):
        user = request.user
        store_id = request.DATA.get('store_id')
        notes = request.DATA.get('notes')
        if store_id and notes:
            updater = None
            if store_type == 'shopify':
                store = ShopifyStore.objects.get(id=store_id)
                permissions.user_can_view(user, store)
                updater = leadgalaxy.utils.ShopifyOrderUpdater(store, pk)
            elif store_type == 'chq':
                store = CommerceHQStore.objects.get(id=store_id)
                permissions.user_can_view(user, store)
                updater = commercehq_core.utils.CHQOrderUpdater(store, pk)

            if updater is not None:
                updater.add_note(notes)
                updater.save_changes()

        return Response({'store_id': store_id, 'store_type': store_type, 'order_no': pk})


class SubUserEmails(APIView):
    def get(self, request):
        user = request.user
        self_email = self.request.GET.get('self')
        emails = []
        if self_email:
            emails.append(user.email)
        for sub_user in User.objects.filter(profile__subuser_parent=user):
            emails.append(sub_user.email)
        return Response({'emails': ','.join(emails)})


class ZapierSampleList(APIView):
    def get(self, request, event):
        """returns a sample for shopify_order, product_disappeared, variant_added, variant_price_changed, variant_quantity_changed, variant_removed"""
        if event == 'shopify_order':
            order = ShopifyOrder(
                id=1,
                store=ShopifyStore(
                    id=1,
                    title='Sample Shopify Store',
                ),
                order_id=386704408627,
                user=request.user,
                order_number=100,
                customer_id=207119551,
                customer_name='Paul Norman',
                customer_email='paul.norman@example.com',
                financial_status='paid',
                fulfillment_status='fulfilled',
                total_price=99.99,
                tags='imported',
                city='Ottawa',
                zip_code='K2P0V6',
                country_code='CA',
                items_count='2',
                created_at=timezone.now(),
                updated_at=timezone.now(),
                closed_at=timezone.now(),
                cancelled_at=timezone.now(),
            )
            sample = order.to_dict()
        elif event in settings.PRICE_MONITOR_EVENTS:
            product_change = ProductChange(
                user=request.user,
                store_type='shopify',
                shopify_product=ShopifyProduct(
                    id=1,
                    title='Sample Shopify Product',
                    store=ShopifyStore(
                        id=1,
                        title='Sample Shopify Store',
                    )
                ),
                data=json.dumps([{
                    'name': 'price',
                    'sku': '14:193#Black;5:202697812#13.3-inch',
                    'old_value': 119.72,
                    'new_value': 129.72,
                    'level': 'variant',
                    'variant_id': 1,
                    'variant_title': 'Sample Variant',
                }, {
                    'name': 'quantity',
                    'sku': '14:193#Black;5:202697812#13.3-inch',
                    'old_value': 5,
                    'new_value': 4,
                    'level': 'variant',
                    'variant_id': 1,
                    'variant_title': 'Sample Variant',
                }, {
                    'name': 'var_added',
                    'sku': '14:193#Black;5:202697812#13.3-inch',
                    'price': 22.1,
                    'availabe_qty': 95,
                    'level': 'variant',
                    'variant_id': 1,
                    'variant_title': 'Sample Variant',
                }, {
                    'name': 'var_added',
                    'sku': '14:193#Black;5:202697812#13.3-inch',
                    'price': 22.1,
                    'availabe_qty': 95,
                    'level': 'variant',
                }, {
                    'name': 'var_removed',
                    'sku': '14:193#Black;5:202697812#13.3-inch',
                    'level': 'variant',
                }, {
                    'name': 'offline',
                    'level': 'product',
                    'new_value': True,
                    'old_value': False,
                }]),
            )
            sample = product_change.to_dict({}, ProductChange.get_category_from_event(event), 0)
        else:
            raise Http404
        return Response([sample])
