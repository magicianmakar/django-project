# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gearbubble_core', '0009_auto_20180520_2222'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='gearbubbleorder',
            name='store',
        ),
        migrations.DeleteModel(
            name='GearBubbleOrder',
        ),
    ]
