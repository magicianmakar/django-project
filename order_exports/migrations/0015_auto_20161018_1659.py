# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0014_auto_20161018_0735'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderexportlog',
            name='csv_url',
            field=models.CharField(default=b'', max_length=512, blank=True),
        ),
        migrations.AddField(
            model_name='orderexportlog',
            name='type',
            field=models.CharField(default=b'sample', max_length=100, choices=[(b'sample', b'Sample file'), (b'complete', b'Complete file')]),
        ),
    ]
