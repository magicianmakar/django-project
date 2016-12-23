# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0145_productsupplier_source_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='bundle_map',
            field=models.TextField(null=True, blank=True),
        ),
    ]
