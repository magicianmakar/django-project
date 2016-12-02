# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0006_auto_20161003_0619'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderexport',
            name='schedule',
            field=models.TimeField(null=True, blank=True),
        ),
    ]
