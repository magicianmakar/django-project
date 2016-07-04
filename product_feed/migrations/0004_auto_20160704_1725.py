# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_feed', '0003_feedstatus_all_variants'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedstatus',
            name='generation_time',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='feedstatus',
            name='updated_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
