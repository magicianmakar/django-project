# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0157_userprofile_orders_track_visited_at'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userprofile',
            name='orders_track_visited_at',
        ),
    ]
