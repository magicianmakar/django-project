# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0035_shopifyproduct_is_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='parent_product',
            field=models.ForeignKey(verbose_name='Dupliacte of product', to='leadgalaxy.ShopifyProduct', null=True, on_delete=django.db.models.deletion.CASCADE),
        ),
    ]
