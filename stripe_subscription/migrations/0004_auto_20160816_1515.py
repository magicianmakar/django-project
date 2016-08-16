# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stripe_subscription', '0003_auto_20160728_1915'),
    ]

    operations = [
        migrations.AlterField(
            model_name='extrastore',
            name='last_invoice',
            field=models.CharField(max_length=64, null=True, verbose_name=b'Last Invoice Item', blank=True),
        ),
    ]
