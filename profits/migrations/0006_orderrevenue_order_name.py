# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-04-22 22:29
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profits', '0005_auto_20190422_2154'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderrevenue',
            name='order_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
