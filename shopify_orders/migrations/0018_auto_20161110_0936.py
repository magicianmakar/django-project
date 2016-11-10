# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0017_shopifyorderline_fulfillment_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyorder',
            name='country_code',
            field=models.CharField(default=b'', max_length=32, null=True, blank=True),
        ),
    ]
