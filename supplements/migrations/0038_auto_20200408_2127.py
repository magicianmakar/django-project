# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2020-04-08 21:27
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0037_auto_20200326_1144'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='usersupplement',
            options={'ordering': ['-pk']},
        ),
        migrations.AddField(
            model_name='usersupplement',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
