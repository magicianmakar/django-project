# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0127_auto_20161114_2030'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productsupplier',
            name='supplier_name',
            field=models.CharField(db_index=True, max_length=512, null=True, blank=True),
        ),
    ]
