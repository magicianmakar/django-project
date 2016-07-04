# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_feed', '0004_auto_20160704_1725'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedstatus',
            name='revision',
            field=models.IntegerField(default=0),
        ),
    ]
