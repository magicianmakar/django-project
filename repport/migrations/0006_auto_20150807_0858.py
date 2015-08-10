# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('repport', '0005_auto_20150807_0856'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='logo',
            field=models.CharField(default=b'', max_length=256, blank=True),
        ),
        migrations.AddField(
            model_name='topic',
            name='action_item',
            field=models.IntegerField(default=0),
        ),
    ]
