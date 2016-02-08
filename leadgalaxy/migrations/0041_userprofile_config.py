# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0040_auto_20151223_1857'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='config',
            field=models.TextField(default=b'', blank=True),
        ),
    ]
