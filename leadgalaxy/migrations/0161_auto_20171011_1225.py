# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0160_auto_20171009_0716'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifystore',
            name='auto_fulfill',
            field=models.CharField(db_index=True, max_length=50, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifystore',
            name='is_active',
            field=models.BooleanField(default=True, db_index=True),
        ),
    ]
