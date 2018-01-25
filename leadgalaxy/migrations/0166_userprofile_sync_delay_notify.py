# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0165_shopifyproduct_monitor_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='sync_delay_notify',
            field=models.IntegerField(default=0, null=True, verbose_name=b'Notify if no tracking number is found (days)', db_index=True),
        ),
    ]
