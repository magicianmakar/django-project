# -*- coding: utf-8 -*-
# Generated by Django 1.11.26 on 2019-11-21 13:55
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0020_auto_20191120_0048'),
    ]

    operations = [
        migrations.AddField(
            model_name='wooordertrack',
            name='errors',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
