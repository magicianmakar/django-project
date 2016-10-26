# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0002_orderexport_sample_url'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='orderexportfilter',
            name='dates',
        ),
        migrations.AddField(
            model_name='orderexport',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now, auto_now_add=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='orderexport',
            name='since_id',
            field=models.CharField(max_length=100, null=True),
        ),
        migrations.DeleteModel(
            name='OrderExportFilterDates',
        ),
    ]
