# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0006_auto_20160429_2239'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorder',
            name='cancelled_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
