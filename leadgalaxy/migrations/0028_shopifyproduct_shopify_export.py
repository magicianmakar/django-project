# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0027_auto_20151218_1627'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='shopify_export',
            field=models.ForeignKey(to='leadgalaxy.ShopifyProductExport', null=True, on_delete=django.db.models.deletion.CASCADE),
        ),
    ]
