# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0164_auto_20171012_1559'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='monitor_id',
            field=models.IntegerField(default=0),
        ),
    ]
