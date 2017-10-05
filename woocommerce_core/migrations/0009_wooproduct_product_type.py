# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0008_wooboard'),
    ]

    operations = [
        migrations.AddField(
            model_name='wooproduct',
            name='product_type',
            field=models.CharField(default=b'', max_length=300, db_index=True, blank=True),
        ),
    ]
