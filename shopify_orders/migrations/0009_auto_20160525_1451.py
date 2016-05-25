# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0008_auto_20160512_1556'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyorder',
            name='tags',
            field=models.TextField(default=b'', null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorderline',
            name='title',
            field=models.TextField(default=b'', null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorderline',
            name='variant_title',
            field=models.TextField(default=b'', null=True, blank=True),
        ),
    ]
