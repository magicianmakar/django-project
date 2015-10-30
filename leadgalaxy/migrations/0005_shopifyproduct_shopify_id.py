# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0004_shopifyproduct_stat'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='shopify_id',
            field=models.IntegerField(default=0, verbose_name=b'Shopif Product ID'),
        ),
    ]
