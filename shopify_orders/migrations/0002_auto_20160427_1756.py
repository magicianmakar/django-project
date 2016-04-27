# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyorder',
            name='created_at',
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='updated_at',
            field=models.DateTimeField(),
        ),
    ]
