# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0024_auto_20170305_1711'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorder',
            name='connected_items',
            field=models.IntegerField(null=True, verbose_name=b'Item Lines with connect products', blank=True),
        ),
        migrations.AddField(
            model_name='shopifyorder',
            name='need_fulfillment',
            field=models.IntegerField(null=True, verbose_name=b'Item Lines not ordered yet', blank=True),
        ),
    ]
