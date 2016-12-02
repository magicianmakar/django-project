# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0017_auto_20161106_0349'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='orderexportquery',
            options={'ordering': ['created_at']},
        ),
        migrations.RemoveField(
            model_name='orderexport',
            name='code',
        ),
        migrations.AddField(
            model_name='orderexportquery',
            name='count',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='orderexportquery',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now, auto_now_add=True),
            preserve_default=False,
        ),
    ]
