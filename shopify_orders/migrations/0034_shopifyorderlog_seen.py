# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-10-03 21:35
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0033_shopifyorderlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorderlog',
            name='seen',
            field=models.IntegerField(default=0),
        ),
    ]
