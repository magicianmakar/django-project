# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0003_woostore_store_hash'),
    ]

    operations = [
        migrations.AddField(
            model_name='wooproduct',
            name='variants_map',
            field=models.TextField(default=b'', blank=True),
        ),
    ]
