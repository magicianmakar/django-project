# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0020_auto_20161211_1708'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyorder',
            name='order_id',
            field=models.BigIntegerField(db_index=True),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='order_number',
            field=models.IntegerField(db_index=True),
        ),
    ]
