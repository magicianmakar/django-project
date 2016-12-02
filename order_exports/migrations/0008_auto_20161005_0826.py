# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0007_auto_20161003_0621'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderexport',
            name='progress',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='orderexport',
            name='receiver',
            field=models.EmailField(max_length=254, null=True, blank=True),
        ),
    ]
