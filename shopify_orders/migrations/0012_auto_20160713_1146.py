# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0011_shopifysyncstatus_pending_orders'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyorderline',
            name='product',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to='leadgalaxy.ShopifyProduct', null=True),
        ),
    ]
