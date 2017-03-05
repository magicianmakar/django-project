# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0022_auto_20170303_1429'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyordershippingline',
            name='code',
            field=models.CharField(max_length=256, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyordershippingline',
            name='source',
            field=models.CharField(max_length=256, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyordershippingline',
            name='title',
            field=models.CharField(db_index=True, max_length=256, null=True, blank=True),
        ),
    ]
