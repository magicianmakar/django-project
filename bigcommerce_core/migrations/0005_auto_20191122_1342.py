# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-11-22 13:42
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bigcommerce_core', '0004_bigcommerceordertrack_errors'),
    ]

    operations = [
        migrations.AddField(
            model_name='bigcommercestore',
            name='uninstalled_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='bigcommerceboard',
            name='title',
            field=models.CharField(blank=True, default='', max_length=512),
        ),
    ]
