# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0107_auto_20160610_2330'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='groupplan',
            name='montly_price',
        ),
    ]
