# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations

import zlib

def convert_zlib_to_plain(apps, schema_editor):
    ShopifyProduct = apps.get_model("leadgalaxy", "ShopifyProduct")

    print '* Begin Product merging for {} products'.format(ShopifyProduct.objects.count())
    print

    merged_products = 0
    empty_products = 0

    for product in ShopifyProduct.objects.all():
        if len(product.original_data):
            product.original_json = zlib.decompress(product.original_data)
            merged_products += 1
        else:
            product.original_json = ''
            empty_products += 1
        product.save()


    print '* Merged Products:', merged_products
    print '* Empty Products:', empty_products

class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0037_shopifyproduct_original_json'),
    ]

    operations = [
        migrations.RunPython(convert_zlib_to_plain),
    ]
