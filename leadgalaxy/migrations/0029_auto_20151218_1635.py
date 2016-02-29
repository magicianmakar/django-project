# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import json

def get_myshopify_link(user, default_store, link):
    stores = [default_store,]
    for i in user.shopifystore_set.all():
        if i not in stores:
            stores.append(i)

    for store in stores:
        handle = link.split('/')[-1]

        r = requests.get(store.get_link('/admin/products.json', api=True), params={'handle': handle}).json()
        if len(r['products']) == 1:
            return store.get_link('/admin/products/{}'.format(r['products'][0]['id']))

        print ' * Product not found in store: {}'.format(store.title)

    return None

def get_product_original_info(product):
    data = json.loads(product.data)

    url = data.get('original_url')
    source = ''

    if url:
        if 'aliexpress' in url.lower():
            source = 'AliExpress'
        elif 'alibaba' in url.lower():
            source = 'AliBaba'

        return {
            'source': source,
            'url': url
        }

    return None

def combine_names(apps, schema_editor):
    ShopifyProduct = apps.get_model("leadgalaxy", "ShopifyProduct")
    ShopifyProductExport = apps.get_model("leadgalaxy", "ShopifyProductExport")

    print
    print '* Begin Product merging for {} products'.format(ShopifyProduct.objects.count())

    merged_products = 0
    problematic_products = 0
    unexported_products = 0

    for product in ShopifyProduct.objects.all():
        if product.shopify_id:
            try:
                # Try to see if it already linked to ShopifyProductExport
                export = ShopifyProductExport.objects.get(product=product)
                product.shopify_export = export
                product.save()

                merged_products += 1
            except:
                # Create a new ShopifyProductExport
                info = get_product_original_info(product)
                if info and info.get('url'):
                    export = ShopifyProductExport(original_url=info.get('url'), shopify_id=product.shopify_id, store=product.store)
                    export.save()

                    product.shopify_export = export
                    product.save()

                    merged_products += 1
                else:
                    problematic_products += 1
                    # print '- Origianl URL not found for product {}'.format(product.id)
        else:
            unexported_products += 1

    print '* Merged Products:', merged_products
    print '* Unexported Products:', unexported_products
    print '* Problematic Products:', problematic_products

class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0028_shopifyproduct_shopify_export'),
    ]

    operations = [
        migrations.RunPython(combine_names),
    ]