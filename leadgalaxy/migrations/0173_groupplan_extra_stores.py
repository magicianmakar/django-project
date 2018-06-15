# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0172_auto_20180614_1433'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='extra_stores',
            field=models.BooleanField(default=True, verbose_name=b'Support adding extra stores'),
        ),
    ]
