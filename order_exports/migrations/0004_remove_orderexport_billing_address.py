# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0003_auto_20160914_0721'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='orderexport',
            name='billing_address',
        ),
    ]
