# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0004_auto_20160428_1221'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyorder',
            name='country_code',
            field=models.CharField(default=b'', max_length=32, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='customer_email',
            field=models.CharField(default=b'', max_length=256, null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='customer_name',
            field=models.CharField(default=b'', max_length=256, null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='tags',
            field=models.CharField(default=b'', max_length=256, null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorderline',
            name='title',
            field=models.CharField(default=b'', max_length=256, db_index=True, blank=True),
        ),
    ]
