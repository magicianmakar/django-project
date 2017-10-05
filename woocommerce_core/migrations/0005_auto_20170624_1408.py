# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0004_wooproduct_variants_map'),
    ]

    operations = [
        migrations.AddField(
            model_name='wooproduct',
            name='mapping_config',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='wooproduct',
            name='shipping_map',
            field=models.TextField(default=b'', null=True, blank=True),
        ),
        migrations.AddField(
            model_name='wooproduct',
            name='supplier_map',
            field=models.TextField(default=b'', null=True, blank=True),
        ),
    ]
