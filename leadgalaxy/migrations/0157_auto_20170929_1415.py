# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0156_shopifyordertrack_errors'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyordertrack',
            name='source_id',
            field=models.CharField(default=b'', max_length=512, verbose_name=b'Source Order ID', db_index=True, blank=True),
        ),
    ]
