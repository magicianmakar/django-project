# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0116_shopifyproduct_supplier_map'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='shipping_map',
            field=models.TextField(default=b'', null=True, blank=True),
        ),
    ]
