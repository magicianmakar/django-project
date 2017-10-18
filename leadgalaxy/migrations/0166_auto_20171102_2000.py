# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0165_shopifyproduct_monitor_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyproduct',
            name='monitor_id',
            field=models.IntegerField(default=0, null=True),
        ),
    ]
