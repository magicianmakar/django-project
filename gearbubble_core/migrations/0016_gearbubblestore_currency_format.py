# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-08-28 19:37
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gearbubble_core', '0015_auto_20190725_2050'),
    ]

    operations = [
        migrations.AddField(
            model_name='gearbubblestore',
            name='currency_format',
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
    ]
