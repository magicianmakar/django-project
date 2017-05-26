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
            name='notes',
            field=models.TextField(null=True, blank=True),
        ),
    ]
