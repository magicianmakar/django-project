# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def convert_base64_to_zlib(apps, schema_editor):
    ShopifyProduct = apps.get_model("leadgalaxy", "ShopifyProduct")

    merged_products = 0

    for product in ShopifyProduct.objects.all():
        product.original_dataz = product.original_data.decode('base64')
        product.save()

        merged_products += 1

    if merged_products:
        print('* Merged Products:', merged_products)


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0031_shopifyproduct_original_dataz'),
    ]

    operations = [
        migrations.RunPython(convert_base64_to_zlib),
    ]
