# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0023_auto_20170304_1458'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyorder',
            name='cancelled_at',
            field=models.DateTimeField(db_index=True, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='closed_at',
            field=models.DateTimeField(db_index=True, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='financial_status',
            field=models.CharField(default=b'', max_length=32, null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='fulfillment_status',
            field=models.CharField(default=b'', max_length=32, null=True, db_index=True, blank=True),
        ),
    ]
