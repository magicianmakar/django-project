# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-07-25 20:50
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0014_wooboard_favorite'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='wooboard',
            options={'ordering': ['title']},
        ),
    ]
