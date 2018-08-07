# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('profit_dashboard', '0012_facebookaccess_expires_in'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='facebookaccess',
            name='campaigns',
        ),
        migrations.AddField(
            model_name='facebookaccount',
            name='campaigns',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.AddField(
            model_name='facebookaccount',
            name='updated_at',
            field=models.DateTimeField(default=datetime.datetime(2018, 8, 3, 8, 40, 58, 881858, tzinfo=utc), auto_now=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='facebookadcost',
            name='campaign_id',
            field=models.CharField(default=b'', max_length=100, null=True),
        ),
    ]
