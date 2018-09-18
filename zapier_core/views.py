import requests

from django.http import Http404
from django.contrib.auth.models import User

from rest_framework import generics, viewsets, mixins
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_hooks.models import Hook

from shopified_core import permissions
from shopified_core.utils import safeFloat, safeInt

from leadgalaxy.models import ShopifyProduct, ShopifyStore, ShopifyOrderTrack
import leadgalaxy.tasks
import leadgalaxy.utils

from commercehq_core.models import CommerceHQProduct, CommerceHQStore, CommerceHQOrderTrack
import commercehq_core.tasks
import commercehq_core.utils

from product_alerts.models import ProductChange

from .payload import get_chq_order_data
from .serializers import *


class HookViewSet(viewsets.ModelViewSet):
    queryset = Hook.objects.all()
    serializer_class = HookSerializer

    def get_queryset(self):
        return Hook.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
        super(HookViewSet, self).perform_create(serializer)


class ShopifyOrderList(generics.ListAPIView):
    serializer_class = ShopifyOrderSerializer

    def get_queryset(self):
        self.store = ShopifyStore.objects.get(id=self.request.GET.get('store_id'))
        permissions.user_can_view(self.request.user, self.store)
        queryset = ShopifyOrder.objects.filter(store=self.store).select_related('store').order_by('-created_at')
        if self.request.GET.get('status') == 'cancelled':
            queryset = queryset.filter(cancelled_at__isnull=False)
        return queryset

    def get_serializer_context(self):
        rep = requests.get(
            url=self.store.get_link('/admin/orders.json', api=True),
            params={
                'ids': ','.join([str(o.order_id) for o in self.object_list]),
                'status': 'any',
                'fulfillment_status': 'any',
                'financial_status': 'any',
            }
        )
        rep.raise_for_status()
        shopify_orders = rep.json()['orders']
        return {
            'data': {str(o['id']): o for o in shopify_orders},
        }

    def list(self, request, *args, **kwargs):
        self.object_list = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(self.object_list)
        if page is not None:
            self.object_list = page
            serializer = self.get_pagination_serializer(page)
        else:
            serializer = self.get_serializer(self.object_list, many=True)

        return Response(serializer.data)


class ShopifyOrderTrackList(generics.ListAPIView):
    serializer_class = ShopifyOrderTrackSerializer

    def get_queryset(self):
        store = ShopifyStore.objects.get(id=self.request.GET.get('store_id'))
        permissions.user_can_view(self.request.user, store)
        queryset = ShopifyOrderTrack.objects.filter(store=store).select_related('store').order_by('-created_at')
        return queryset


class CommerceHQOrderTrackList(generics.ListAPIView):
    serializer_class = CommerceHQOrderTrackSerializer

    def get_queryset(self):
        store = CommerceHQStore.objects.get(id=self.request.GET.get('store_id'))
        permissions.user_can_view(self.request.user, store)
        queryset = CommerceHQOrderTrack.objects.filter(store=store).select_related('store').order_by('-created_at')
        return queryset


class ProductAlertList(generics.ListAPIView):
    serializer_class = ProductAlertSerializer

    def get_queryset(self):
        queryset = ProductChange.objects.filter(user=self.request.user).order_by('-created_at')
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(categories__icontains=category)
        store_type = self.request.GET.get('store_type')
        if store_type:
            queryset = queryset.filter(store_type=store_type)
            if store_type == 'shopify':
                if self.request.GET.get('store_id'):
                    queryset = queryset.filter(shopify_product__store_id=self.request.GET.get('store_id'))
                if self.request.GET.get('product_id'):
                    queryset = queryset.filter(shopify_product_id=self.request.GET.get('product_id'))
                queryset = queryset.select_related('shopify_product', 'shopify_product__store')
            if store_type == 'chq' and self.request.GET.get('store_id'):
                if self.request.GET.get('store_id'):
                    queryset = queryset.filter(chq_product__store_id=self.request.GET.get('store_id'))
                if self.request.GET.get('product_id'):
                    queryset = queryset.filter(chq_product_id=self.request.GET.get('product_id'))
                queryset = queryset.select_related('chq_product', 'chq_product__store')

        return queryset

    def get_serializer_context(self):
        return {
            'category': self.request.GET.get('category'),
        }

    def list(self, request, *args, **kwargs):
        self.object_list = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(self.object_list)
        if page is not None:
            serializer = self.get_pagination_serializer(page)
        else:
            serializer = self.get_serializer(self.object_list, many=True)

        return Response(serializer.data)


class ProductChangesList(generics.ListAPIView):
    serializer_class = ProductChangeSerializer

    def get_queryset(self):
        queryset = ProductChange.objects.filter(user=self.request.user).order_by('-created_at')
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(categories__icontains=category)
        store_type = self.request.GET.get('store_type')
        if store_type:
            queryset = queryset.filter(store_type=store_type)
            if store_type == 'shopify':
                if self.request.GET.get('store_id'):
                    queryset = queryset.filter(shopify_product__store_id=self.request.GET.get('store_id'))
                if self.request.GET.get('product_id'):
                    queryset = queryset.filter(shopify_product_id=self.request.GET.get('product_id'))
                queryset = queryset.select_related('shopify_product', 'shopify_product__store')
            if store_type == 'chq' and self.request.GET.get('store_id'):
                if self.request.GET.get('store_id'):
                    queryset = queryset.filter(chq_product__store_id=self.request.GET.get('store_id'))
                if self.request.GET.get('product_id'):
                    queryset = queryset.filter(chq_product_id=self.request.GET.get('product_id'))
                queryset = queryset.select_related('chq_product', 'chq_product__store')

        return queryset

    def get_serializer_context(self):
        return {
            'category': self.request.GET.get('category'),
            'change_index': 0,
        }

    def list(self, request, *args, **kwargs):
        self.object_list = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(self.object_list)
        if page is not None:
            serializer = self.get_pagination_serializer(page)
        else:
            serializer = self.get_serializer(self.object_list, many=True)

        return Response(serializer.data)


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
        queryset = queryset.select_related('store')
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
        queryset = queryset.select_related('store')
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


class OrderDetail(APIView):
    def get(self, request, pk, store_type):
        user = request.user
        store_id = request.GET.get('store_id')
        ret = {}
        if store_type == 'shopify':
            store = ShopifyStore.objects.get(id=store_id)
            permissions.user_can_view(user, store)
            order_data = leadgalaxy.utils.get_shopify_order(store, pk)
            ret = get_shopify_order_data(store, order_data)
        elif store_type == 'chq':
            store = CommerceHQStore.objects.get(id=store_id)
            permissions.user_can_view(user, store)
            order_data = commercehq_core.utils.get_chq_order(store, pk)
            ret = get_chq_order_data(store, order_data)

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
