# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0012_auto_20160713_1146'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyorder',
            name='customer_email',
            field=models.CharField(default=b'', max_length=256, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='customer_name',
            field=models.CharField(default=b'', max_length=256, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='tags',
            field=models.TextField(default=b'', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorderline',
            name='title',
            field=models.TextField(default=b'', null=True, blank=True),
        ),
    ]
