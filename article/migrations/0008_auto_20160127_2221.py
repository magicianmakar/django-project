# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0007_auto_20160126_2105'),
    ]

    operations = [
        migrations.AddField(
            model_name='sidebarlink',
            name='icon',
            field=models.CharField(default=b'', max_length=20, blank=True),
        ),
        migrations.AddField(
            model_name='sidebarlink',
            name='new_tab',
            field=models.BooleanField(default=False),
        ),
    ]
