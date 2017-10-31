# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dropwow_core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='dropwoworderstatus',
            name='pending',
            field=models.BooleanField(default=False),
        ),
    ]
