# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0112_auto_20160723_2227'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='shopifystore',
            options={'ordering': ['list_index', '-created_at']},
        ),
        migrations.AddField(
            model_name='shopifystore',
            name='list_index',
            field=models.IntegerField(default=0),
        ),
    ]
