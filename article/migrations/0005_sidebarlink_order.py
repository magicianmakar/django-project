# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0004_sidebarlink'),
    ]

    operations = [
        migrations.AddField(
            model_name='sidebarlink',
            name='order',
            field=models.IntegerField(default=0),
        ),
    ]
