# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0162_auto_20171012_1552'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyordertrack',
            name='source_id',
            field=models.CharField(default='', max_length=512, verbose_name='Source Order ID', db_index=True, blank=True),
        ),
    ]
