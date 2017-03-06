# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='commercehqboard',
            name='config',
            field=models.CharField(default=b'', max_length=512, blank=True),
        ),
    ]
