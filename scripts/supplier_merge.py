import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")
django.setup()

from leadgalaxy.models import *
from django.db.models import Q
from django.db import transaction


def get_shopify_id(product):
    try:
        return product.shopify_export.shopify_id
    except:
        return None


def get_shopify_exports(product):
    shopify_id = get_shopify_id(product)
    if shopify_id:
        return ShopifyProductExport.objects.filter(
            Q(shopify_id=product.shopify_export.shopify_id, store__user=product.user) |
            Q(product=product))
    else:
        return ShopifyProductExport.objects.filter(product=product)


def merge_suppliers(debug=False):
    count = 0
    for product in ShopifyProduct.objects.defer('data') \
                                         .select_related('store', 'shopify_export') \
                                         .exclude(shopify_export=None) \
                                         .exclude(shopify_id__gt=0):

        last_export, last_supplier = None, None
        for export in get_shopify_exports(product).order_by('created_at'):
            is_default = product.shopify_export_id == export.id
            last_export = export

            if debug:
                print 'Default' if is_default else ' '*7, \
                    export.shopify_id, \
                    export.supplier_name, \
                    export.supplier_url

            supplier_url = export.supplier_url
            if supplier_url and supplier_url.startswith('//'):
                supplier_url = u'http:{}'.format(supplier_url)

            last_supplier = ProductSupplier.objects.create(
                store=product.store,
                product=product,
                product_url=export.original_url,
                supplier_name=export.supplier_name,
                supplier_url=supplier_url,
                is_default=is_default,
                variants_map=product.variants_map if is_default else None)

        if last_supplier:
            product.default_supplier = last_supplier
            product.shopify_id = last_export.shopify_id
            product.save()

        count += 1

        if count % 100 == 0:
            print count,

print 'Before Connected:', ShopifyProduct.objects.exclude(shopify_export=None).count()


total = ShopifyProduct.objects.defer('data') \
                              .select_related('store', 'shopify_export') \
                              .exclude(shopify_export=None) \
                              .exclude(shopify_id__gt=0).count()

print 'Total:', total

with transaction.atomic():
    merge_suppliers(not True)

print ' After Connected:', ShopifyProduct.objects.exclude(shopify_export=None).count()
