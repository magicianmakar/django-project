# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0102_auto_20160511_1836'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyproduct',
            name='tag',
            field=models.TextField(default='', db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyproduct',
            name='title',
            field=models.TextField(default='', db_index=True, blank=True),
        ),
    ]
