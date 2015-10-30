# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0005_shopifyproduct_shopify_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyproduct',
            name='shopify_id',
            field=models.BigIntegerField(default=0, verbose_name=b'Shopif Product ID'),
        ),
    ]
