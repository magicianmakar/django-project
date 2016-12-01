# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0128_shopifyproduct_config'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyproduct',
            name='config',
            field=models.TextField(null=True, blank=True),
        ),
    ]
