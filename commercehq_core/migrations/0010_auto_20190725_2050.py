# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-07-25 20:50
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0009_commercehqboard_favorite'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='commercehqboard',
            options={'ordering': ['title']},
        ),
    ]
