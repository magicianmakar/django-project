# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0025_shopifyproductexport'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproductexport',
            name='product',
            field=models.ForeignKey(to='leadgalaxy.ShopifyProduct', null=True, on_delete=django.db.models.deletion.CASCADE),
        ),
    ]
