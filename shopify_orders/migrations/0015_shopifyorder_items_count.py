# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0014_shopifyorderline_track'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorder',
            name='items_count',
            field=models.IntegerField(null=True, verbose_name=b'Item Lines count', blank=True),
        ),
    ]
