# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0081_auto_20160306_1436'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorder',
            name='shopify_status',
            field=models.CharField(default=b'', max_length=128, null=True, verbose_name=b'Shopify Fulfillment Status', blank=True),
        ),
    ]
