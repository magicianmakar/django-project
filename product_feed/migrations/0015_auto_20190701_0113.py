# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-07-01 01:13
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_feed', '0014_groovekartfeedstatus'),
    ]

    operations = [
        migrations.AddField(
            model_name='commercehqfeedstatus',
            name='google_access_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Last Google Access'),
        ),
        migrations.AddField(
            model_name='feedstatus',
            name='google_access_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Last Google Access'),
        ),
        migrations.AddField(
            model_name='gearbubblefeedstatus',
            name='google_access_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Last Google Access'),
        ),
        migrations.AddField(
            model_name='groovekartfeedstatus',
            name='google_access_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Last Google Access'),
        ),
        migrations.AddField(
            model_name='woofeedstatus',
            name='google_access_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Last Google Access'),
        ),
    ]
