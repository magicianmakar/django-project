# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0008_auto_20161005_0826'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderexport',
            name='progress',
            field=models.IntegerField(null=True, blank=True),
        ),
    ]
