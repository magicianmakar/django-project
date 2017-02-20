# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0136_auto_20170209_2009'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='auto_fulfill_limit',
            field=models.IntegerField(default=-1, verbose_name=b'Auto Fulfill Limit'),
        ),
        migrations.AlterField(
            model_name='groupplan',
            name='boards',
            field=models.IntegerField(default=0, verbose_name=b'Boards Limit'),
        ),
        migrations.AlterField(
            model_name='groupplan',
            name='products',
            field=models.IntegerField(default=0, verbose_name=b'Products Limit'),
        ),
        migrations.AlterField(
            model_name='groupplan',
            name='stores',
            field=models.IntegerField(default=0, verbose_name=b'Stores Limit'),
        ),
    ]
