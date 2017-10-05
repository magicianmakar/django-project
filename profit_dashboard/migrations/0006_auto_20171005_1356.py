# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profit_dashboard', '0005_auto_20171004_2339'),
    ]

    operations = [
        migrations.AlterField(
            model_name='facebookaccess',
            name='campaigns',
            field=models.TextField(null=True, blank=True),
        ),
    ]
