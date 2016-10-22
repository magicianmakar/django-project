# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0016_auto_20160928_2321'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorderline',
            name='fulfillment_status',
            field=models.TextField(null=True, blank=True),
        ),
    ]
