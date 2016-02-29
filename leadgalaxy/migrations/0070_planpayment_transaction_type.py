# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0069_auto_20160222_2150'),
    ]

    operations = [
        migrations.AddField(
            model_name='planpayment',
            name='transaction_type',
            field=models.CharField(max_length=32, blank=True),
        ),
    ]
