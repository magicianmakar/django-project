# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0006_auto_20171006_1825'),
    ]

    operations = [
        migrations.AddField(
            model_name='commercehqproduct',
            name='monitor_id',
            field=models.IntegerField(null=True),
        ),
    ]
