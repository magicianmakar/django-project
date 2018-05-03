# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0169_groupplan_locked'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifystore',
            name='info',
            field=models.TextField(null=True, blank=True),
        ),
    ]
