# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0100_remove_shopifyproduct_stat'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='price',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='product_type',
            field=models.CharField(default=b'', max_length=255, db_index=True, blank=True),
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='tag',
            field=models.CharField(default=b'', max_length=255, db_index=True, blank=True),
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='title',
            field=models.CharField(default=b'', max_length=512, db_index=True, blank=True),
        ),
    ]
