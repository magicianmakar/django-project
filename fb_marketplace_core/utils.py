import copy
import json
import re

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404

from shopified_core import permissions
from shopified_core.utils import products_filter, safe_int

from .models import FBMarketplaceBoard, FBMarketplaceProduct, FBMarketplaceStore


def fb_marketplace_products(request, post_per_page=25, sort=None, board=None, store='n'):
    store = request.GET.get('store', store)
    sort = request.GET.get('sort')

    user_stores = request.user.profile.get_fb_marketplace_stores(flat=True)
    res = FBMarketplaceProduct.objects.select_related('store') \
                              .filter(user=request.user.models_user) \
                              .filter(Q(store__in=user_stores) | Q(store=None))

    if store:
        if store == 'c':  # connected
            res = res.exclude(source_id=0)
        elif store == 'n':  # non-connected
            res = res.filter(source_id=0)

            in_store = safe_int(request.GET.get('in'))
            if in_store:
                in_store = get_object_or_404(FBMarketplaceStore, id=in_store)
                res = res.filter(store=in_store)

                permissions.user_can_view(request.user, in_store)
        else:
            store = get_object_or_404(FBMarketplaceStore, id=store)
            res = res.filter(source_id__gt=0, store=store)

            permissions.user_can_view(request.user, store)

    if board:
        res = res.filter(fbmarketplaceboard=board)
        permissions.user_can_view(request.user, get_object_or_404(FBMarketplaceBoard, id=board))

    res = products_filter(res, request.GET)

    if sort:
        if re.match(r'^-?(title|price)$', sort):
            res = res.order_by(sort)

    return res


@transaction.atomic
def duplicate_product(product, store=None):
    parent_product = FBMarketplaceProduct.objects.get(id=product.id)
    product = copy.deepcopy(parent_product)
    product.parent_product = parent_product
    product.pk = None
    product.source_id = 0
    product.source_slug = ''
    if store is not None:
        product.store = store
    data = product.parsed
    product.data = json.dumps(data)
    product.save()

    for supplier in parent_product.fbmarketplacesupplier_set.all():
        supplier.pk = None
        supplier.product = product
        supplier.store = product.store
        supplier.save()

        if supplier.is_default:
            product.set_default_supplier(supplier, commit=True)

    return product
