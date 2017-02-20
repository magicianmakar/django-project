# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0004_auto_20170217_2305'),
    ]

    operations = [
        migrations.AddField(
            model_name='commercehqstore',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='commercehqstore',
            name='store_hash',
            field=models.CharField(default=b'', unique=True, max_length=50, editable=False),
        ),
    ]
