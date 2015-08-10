# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('repport', '0002_auto_20150731_1213'),
    ]

    operations = [
        migrations.AddField(
            model_name='categorie',
            name='created_at',
            field=models.DateTimeField(default=datetime.datetime(2015, 7, 31, 15, 13, 3, 4250, tzinfo=utc), verbose_name=b'Creation Date', auto_now_add=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='categorie',
            name='updated_at',
            field=models.DateTimeField(default=datetime.datetime(2015, 7, 31, 15, 13, 7, 433302, tzinfo=utc), verbose_name=b'Last Update', auto_now=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='topic',
            name='created_at',
            field=models.DateTimeField(default=datetime.datetime(2015, 7, 31, 15, 13, 12, 469006, tzinfo=utc), verbose_name=b'Creation Date', auto_now_add=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='topic',
            name='updated_at',
            field=models.DateTimeField(default=datetime.datetime(2015, 7, 31, 15, 13, 18, 110274, tzinfo=utc), verbose_name=b'Last Update', auto_now=True),
            preserve_default=False,
        ),
    ]
