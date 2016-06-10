# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0010_shopifysyncstatus_orders_count'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifysyncstatus',
            name='pending_orders',
            field=models.TextField(null=True, blank=True),
        ),
    ]
