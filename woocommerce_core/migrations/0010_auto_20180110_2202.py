# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0009_wooproduct_product_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wooordertrack',
            name='source_id',
            field=models.CharField(default='', max_length=512, verbose_name='Source Order ID', db_index=True, blank=True),
        ),
    ]
