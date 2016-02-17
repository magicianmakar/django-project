# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0062_shopifyproduct_price_notification_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorder',
            name='check_count',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='shopifyorder',
            name='status_updated_at',
            field=models.DateTimeField(default=datetime.datetime(2016, 2, 17, 0, 41, 24, 999112, tzinfo=utc), verbose_name=b'Last Status Update', auto_now_add=True),
            preserve_default=False,
        ),
    ]
