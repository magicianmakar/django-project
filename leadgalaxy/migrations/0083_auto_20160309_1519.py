# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0082_shopifyorder_shopify_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='planregistration',
            name='data',
            field=models.TextField(default=b'', blank=True),
        ),
    ]
