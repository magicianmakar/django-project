# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gearbubble_core', '0008_gearbubbleproduct_source_slug'),
    ]

    operations = [
        migrations.AddField(
            model_name='gearbubbleorder',
            name='is_shipped',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='gearbubbleorder',
            name='status',
            field=models.CharField(default=b'', max_length=128),
        ),
    ]
