# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0004_remove_orderexport_billing_address'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderexport',
            name='previous_day',
            field=models.BooleanField(default=True),
        ),
    ]
