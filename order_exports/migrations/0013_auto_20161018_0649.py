# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0012_auto_20161018_0549'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderexport',
            name='progress',
            field=models.IntegerField(default=0, null=True, blank=True),
        ),
    ]
