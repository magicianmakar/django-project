# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0174_groupplan_trial_days'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifystore',
            name='primary_location',
            field=models.BigIntegerField(null=True, blank=True),
        ),
    ]
