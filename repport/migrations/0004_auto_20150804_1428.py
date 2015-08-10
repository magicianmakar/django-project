# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('repport', '0003_auto_20150731_1513'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='url',
            field=models.CharField(max_length=256, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='project',
            name='website',
            field=models.CharField(max_length=256, null=True, blank=True),
        ),
    ]
