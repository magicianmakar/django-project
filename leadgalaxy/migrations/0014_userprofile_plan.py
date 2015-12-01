# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0013_userprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='plan',
            field=models.ForeignKey(to='leadgalaxy.GroupPlan'),
            preserve_default=False,
        ),
    ]
