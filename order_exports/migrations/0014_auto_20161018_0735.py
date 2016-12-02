# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0013_auto_20161018_0649'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderexportlog',
            name='finished_by',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
