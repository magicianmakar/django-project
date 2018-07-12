# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0173_groupplan_extra_stores'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='trial_days',
            field=models.IntegerField(default=0),
        ),
    ]
