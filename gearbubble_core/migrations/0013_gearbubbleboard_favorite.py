# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2019-01-22 02:00
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gearbubble_core', '0012_gearbubbleordertrack_source_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='gearbubbleboard',
            name='favorite',
            field=models.BooleanField(default=False),
        ),
    ]
