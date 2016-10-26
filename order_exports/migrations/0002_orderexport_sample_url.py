# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderexport',
            name='sample_url',
            field=models.CharField(default=b'', max_length=512, blank=True),
        ),
    ]
