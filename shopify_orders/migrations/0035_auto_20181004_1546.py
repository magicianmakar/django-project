# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-10-04 15:46
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0034_shopifyorderlog_seen'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyorderlog',
            name='seen',
            field=models.IntegerField(blank=True, default=0, null=True),
        ),
    ]
