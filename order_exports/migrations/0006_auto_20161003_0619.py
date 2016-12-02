# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0005_orderexport_previous_day'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderexportfilter',
            name='created_at_max',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='orderexportfilter',
            name='created_at_min',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
