# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0120_auto_20161013_2244'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifystore',
            name='auto_fulfill',
            field=models.CharField(max_length=50, null=True, blank=True),
        ),
    ]
