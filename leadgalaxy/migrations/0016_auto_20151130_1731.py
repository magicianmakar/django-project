# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0015_remove_groupplan_group'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='plan',
            field=models.ForeignKey(to='leadgalaxy.GroupPlan', null=True, on_delete=django.db.models.deletion.CASCADE),
        ),
    ]
