# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0007_shopifyorder_cancelled_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifysyncstatus',
            name='sync_status',
            field=models.IntegerField(default=0, choices=[(0, b'Pending'), (1, b'Started'), (2, b'Completed'), (3, b'Unauthorized'), (4, b'Error'), (5, b'Disabled')]),
        ),
    ]
