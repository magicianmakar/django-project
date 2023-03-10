# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-11-06 16:54
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0018_woostore_currency_format'),
    ]

    operations = [
        migrations.AddField(
            model_name='woostore',
            name='api_string_auth',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='woostore',
            name='api_timeout',
            field=models.IntegerField(default=30),
        ),
        migrations.AddField(
            model_name='woostore',
            name='api_version',
            field=models.CharField(default='wc/v2', max_length=50),
        ),
    ]
