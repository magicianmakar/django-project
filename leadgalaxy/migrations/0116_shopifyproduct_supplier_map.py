# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0115_productsupplier_is_default'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='supplier_map',
            field=models.TextField(default=b'', null=True, blank=True),
        ),
    ]
