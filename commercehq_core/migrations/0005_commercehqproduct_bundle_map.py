# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0004_auto_20170420_2024'),
    ]

    operations = [
        migrations.AddField(
            model_name='commercehqproduct',
            name='bundle_map',
            field=models.TextField(null=True, blank=True),
        ),
    ]
