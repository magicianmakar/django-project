# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0159_usercompany_vat'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyordertrack',
            name='source_id',
            field=models.CharField(default='', max_length=512, verbose_name='Source Order ID', blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyordertrack',
            name='source_tracking',
            field=models.CharField(default='', max_length=128, verbose_name='Source Tracking Number', db_index=True, blank=True),
        ),
    ]
