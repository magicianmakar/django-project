# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0167_auto_20180206_1408'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifystore',
            name='currency_format',
            field=models.CharField(max_length=512, null=True, blank=True),
        ),
    ]
