# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gearbubble_core', '0007_gearbubbleorder'),
    ]

    operations = [
        migrations.AddField(
            model_name='gearbubbleproduct',
            name='source_slug',
            field=models.CharField(default=b'', max_length=300, blank=True),
        ),
    ]
