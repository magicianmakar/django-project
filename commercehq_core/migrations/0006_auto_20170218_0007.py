# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0005_auto_20170217_2314'),
    ]

    operations = [
        migrations.RenameField(
            model_name='commercehqstore',
            old_name='url',
            new_name='api_url',
        ),
    ]
