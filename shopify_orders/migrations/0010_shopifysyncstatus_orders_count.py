# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0009_auto_20160525_1451'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifysyncstatus',
            name='orders_count',
            field=models.IntegerField(default=0),
        ),
    ]
