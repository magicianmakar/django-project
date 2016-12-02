# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0011_auto_20161017_2228'),
    ]

    operations = [
        migrations.RenameField(
            model_name='orderexportlog',
            old_name='created_at',
            new_name='started_by',
        ),
        migrations.AddField(
            model_name='orderexportlog',
            name='finished_by',
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
