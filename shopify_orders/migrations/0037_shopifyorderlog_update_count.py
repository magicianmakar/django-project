# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-03-21 23:31
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0036_auto_20181004_1558'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorderlog',
            name='update_count',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]