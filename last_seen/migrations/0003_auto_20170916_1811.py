# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('last_seen', '0002_auto_20170916_1517'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='lastseen',
            unique_together=set([]),
        ),
    ]
