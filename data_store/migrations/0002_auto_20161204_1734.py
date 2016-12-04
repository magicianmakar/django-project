# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('data_store', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='datastore',
            name='key',
            field=models.CharField(unique=True, max_length=32),
        ),
    ]
