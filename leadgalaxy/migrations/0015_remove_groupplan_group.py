# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0014_userprofile_plan'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='groupplan',
            name='group',
        ),
    ]
