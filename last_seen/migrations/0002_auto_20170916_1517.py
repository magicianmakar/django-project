# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('last_seen', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lastseen',
            name='module',
            field=models.CharField(default='website', max_length=20),
        ),
    ]
