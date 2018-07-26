# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gearbubble_core', '0002_auto_20180304_1651'),
    ]

    operations = [
        migrations.AddField(
            model_name='gearbubblestore',
            name='store_hash',
            field=models.CharField(default=b'', max_length=50, editable=False),
        ),
    ]
