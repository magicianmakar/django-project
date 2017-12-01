# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0031_shopifyorderrisk'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifysyncstatus',
            name='elastic',
            field=models.BooleanField(default=False),
        ),
    ]
