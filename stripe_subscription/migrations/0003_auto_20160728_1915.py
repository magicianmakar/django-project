# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stripe_subscription', '0002_extrastore'),
    ]

    operations = [
        migrations.AddField(
            model_name='extrastore',
            name='last_invoice',
            field=models.CharField(default=b'Last Invoice Item', max_length=64, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='extrastore',
            name='status',
            field=models.CharField(default=b'pending', max_length=64, null=True, blank=True),
        ),
    ]
