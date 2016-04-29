# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0005_auto_20160428_1541'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyorder',
            name='city',
            field=models.CharField(default=b'', max_length=64, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='country_code',
            field=models.CharField(default=b'', max_length=32, null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='financial_status',
            field=models.CharField(default=b'', max_length=32, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='zip_code',
            field=models.CharField(default=b'', max_length=32, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorderline',
            name='title',
            field=models.CharField(default=b'', max_length=256, null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorderline',
            name='variant_title',
            field=models.CharField(default=b'', max_length=64, null=True, blank=True),
        ),
    ]
