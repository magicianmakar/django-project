# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0002_auto_20160427_1756'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorder',
            name='closed_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
