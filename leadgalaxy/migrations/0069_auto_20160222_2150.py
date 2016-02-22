# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0068_auto_20160222_2145'),
    ]

    operations = [
        migrations.AddField(
            model_name='planpayment',
            name='email',
            field=models.CharField(max_length=120, blank=True),
        ),
        migrations.AddField(
            model_name='planpayment',
            name='fullname',
            field=models.CharField(max_length=120, blank=True),
        ),
    ]
