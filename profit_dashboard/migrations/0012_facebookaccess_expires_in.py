# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profit_dashboard', '0011_auto_20180511_2157'),
    ]

    operations = [
        migrations.AddField(
            model_name='facebookaccess',
            name='expires_in',
            field=models.DateTimeField(default=None, null=True, blank=True),
        ),
    ]
