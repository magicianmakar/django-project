# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0004_auto_20170616_2324'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderexportquery',
            name='found_order_ids',
            field=models.TextField(default=b''),
        ),
        migrations.AddField(
            model_name='orderexportquery',
            name='found_vendors',
            field=models.TextField(default=b''),
        ),
    ]
