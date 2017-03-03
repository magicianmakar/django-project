# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0021_auto_20170303_1148'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyorder',
            name='order_id',
            field=models.BigIntegerField(),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='order_number',
            field=models.IntegerField(),
        ),
    ]
