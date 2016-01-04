# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0042_auto_20160104_1725'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyproduct',
            name='parent_product',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, verbose_name=b'Dupliacte of product', blank=True, to='leadgalaxy.ShopifyProduct', null=True),
        ),
        migrations.AlterField(
            model_name='shopifyproduct',
            name='shopify_export',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, blank=True, to='leadgalaxy.ShopifyProductExport', null=True),
        ),
    ]
