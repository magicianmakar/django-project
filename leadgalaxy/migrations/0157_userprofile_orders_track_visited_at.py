# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0156_shopifyordertrack_errors'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='orders_track_visited_at',
            field=models.DateTimeField(null=True, verbose_name=b'Plan Expire Date', blank=True),
        ),
    ]
