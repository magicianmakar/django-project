# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0151_auto_20170721_2230'),
    ]

    operations = [
        migrations.AlterField(
            model_name='groupplan',
            name='monthly_price',
            field=models.DecimalField(null=True, verbose_name=b'Monthly Price(in USD)', max_digits=9, decimal_places=2, blank=True),
        ),
    ]
