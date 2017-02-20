# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0135_auto_20170117_2158'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifystore',
            name='uninstalled_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifystore',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='shopifystore',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
