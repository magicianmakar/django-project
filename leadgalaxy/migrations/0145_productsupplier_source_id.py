# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0144_shopifyproduct_is_excluded'),
    ]

    operations = [
        migrations.AddField(
            model_name='productsupplier',
            name='source_id',
            field=models.CharField(db_index=True, max_length=512, null=True, blank=True),
        ),
    ]
