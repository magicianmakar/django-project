# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profit_dashboard', '0009_auto_20171214_2255'),
    ]

    operations = [
        migrations.AddField(
            model_name='facebookaccount',
            name='config',
            field=models.CharField(default='selected', max_length=100, choices=[('include', 'Include Selected Campaign Only'), ('include_and_new', 'Include Selected Campaign and newer ones'), ('exclude', 'Exclude Selected Campaign')]),
        ),
    ]
