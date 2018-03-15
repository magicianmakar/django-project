# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0168_auto_20180302_1801'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='locked',
            field=models.BooleanField(default=False, verbose_name=b'Disable Direct Subscription'),
        ),
    ]
