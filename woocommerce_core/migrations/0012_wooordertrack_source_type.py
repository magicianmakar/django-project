# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-11-08 21:33
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0011_woouserupload'),
    ]

    operations = [
        migrations.AddField(
            model_name='wooordertrack',
            name='source_type',
            field=models.CharField(blank=True, max_length=512, null=True, verbose_name=b'Source Type'),
        ),
    ]