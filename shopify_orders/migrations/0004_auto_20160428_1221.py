# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0003_shopifyorder_closed_at'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='shopifyorder',
            options={},
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='order_id',
            field=models.BigIntegerField(),
        ),
        migrations.AlterUniqueTogether(
            name='shopifyorder',
            unique_together=set([('store', 'order_id')]),
        ),
    ]
