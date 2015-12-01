# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0016_auto_20151130_1731'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='badge_image',
            field=models.CharField(default=b'', max_length=512, blank=True),
        ),
        migrations.AddField(
            model_name='groupplan',
            name='description',
            field=models.CharField(default=b'', max_length=512, blank=True),
        ),
    ]
