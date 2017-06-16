# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderexportfilter',
            name='product_price_max',
            field=models.FloatField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='orderexportfilter',
            name='product_price_min',
            field=models.FloatField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='orderexportfilter',
            name='product_title',
            field=models.TextField(default=b'', null=True, blank=True),
        ),
    ]
