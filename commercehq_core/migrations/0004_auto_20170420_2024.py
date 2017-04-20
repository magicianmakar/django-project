# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0003_commercehquserupload'),
    ]

    operations = [
        migrations.AddField(
            model_name='commercehqstore',
            name='auto_fulfill',
            field=models.CharField(max_length=50, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='commercehqstore',
            name='list_index',
            field=models.IntegerField(default=0),
        ),
    ]
