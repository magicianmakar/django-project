# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0056_auto_20160130_1230'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorder',
            name='source_status',
            field=models.CharField(default=b'', max_length=128, verbose_name=b'Source Order Status', blank=True),
        ),
        migrations.AddField(
            model_name='shopifyorder',
            name='source_tracking',
            field=models.CharField(default=b'', max_length=128, verbose_name=b'Source Tracking Number', blank=True),
        ),
        migrations.AddField(
            model_name='shopifyorder',
            name='updated_at',
            field=models.DateTimeField(default=datetime.datetime(2016, 1, 30, 15, 9, 33, 428757, tzinfo=utc), verbose_name=b'Last update', auto_now=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='data',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='source_id',
            field=models.BigIntegerField(default=0, verbose_name=b'Source Order ID'),
        ),
    ]
