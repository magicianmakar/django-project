# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0015_auto_20161018_1659'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='orderexportlog',
            name='error',
        ),
        migrations.AddField(
            model_name='orderexport',
            name='copy_me',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='orderexport',
            name='receiver',
            field=models.TextField(null=True, blank=True),
        ),
    ]
