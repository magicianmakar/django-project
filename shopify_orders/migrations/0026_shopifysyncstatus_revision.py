# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0025_auto_20170517_1921'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifysyncstatus',
            name='revision',
            field=models.IntegerField(default=1),
        ),
    ]
