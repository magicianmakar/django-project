# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0094_auto_20160401_1342'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='boards',
            field=models.IntegerField(default=-2),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='products',
            field=models.IntegerField(default=-2),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='stores',
            field=models.IntegerField(default=-2),
        ),
    ]
