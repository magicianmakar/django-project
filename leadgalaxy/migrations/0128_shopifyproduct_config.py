# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0127_auto_20161114_2030'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='config',
            field=models.TextField(default=b'', blank=True),
        ),
    ]
