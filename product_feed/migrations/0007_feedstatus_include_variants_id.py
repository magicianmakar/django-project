# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_feed', '0006_auto_20160704_1912'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedstatus',
            name='include_variants_id',
            field=models.BooleanField(default=True),
        ),
    ]
