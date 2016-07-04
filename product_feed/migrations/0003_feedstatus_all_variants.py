# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_feed', '0002_auto_20160704_1609'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedstatus',
            name='all_variants',
            field=models.BooleanField(default=True),
        ),
    ]
