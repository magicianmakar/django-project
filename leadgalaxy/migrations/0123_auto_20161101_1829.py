# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0122_auto_20161020_1340'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyproduct',
            name='shopify_id',
            field=models.BigIntegerField(default=0, null=True, db_index=True, blank=True),
        ),
    ]
