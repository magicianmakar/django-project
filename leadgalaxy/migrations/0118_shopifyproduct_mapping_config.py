# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0117_shopifyproduct_shipping_map'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='mapping_config',
            field=models.TextField(null=True, blank=True),
        ),
    ]
