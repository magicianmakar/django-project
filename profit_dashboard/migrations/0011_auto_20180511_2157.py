# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profit_dashboard', '0010_facebookaccount_config'),
    ]

    operations = [
        migrations.AlterField(
            model_name='facebookaccess',
            name='account_ids',
            field=models.CharField(default=b'', max_length=255, blank=True),
        ),
        migrations.AlterField(
            model_name='facebookaccess',
            name='campaigns',
            field=models.TextField(default=b'', blank=True),
        ),
    ]
