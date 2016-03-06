# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0080_auto_20160305_1427'),
    ]

    operations = [
        migrations.AlterField(
            model_name='featurebundle',
            name='register_hash',
            field=models.CharField(unique=True, max_length=50, editable=False),
        ),
        migrations.AlterField(
            model_name='groupplan',
            name='register_hash',
            field=models.CharField(unique=True, max_length=50, editable=False),
        ),
        migrations.AlterField(
            model_name='planregistration',
            name='register_hash',
            field=models.CharField(unique=True, max_length=40, editable=False),
        ),
    ]
