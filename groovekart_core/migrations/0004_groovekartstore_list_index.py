# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-06-30 15:00
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('groovekart_core', '0003_groovekartuserupload'),
    ]

    operations = [
        migrations.AddField(
            model_name='groovekartstore',
            name='list_index',
            field=models.IntegerField(default=0),
        ),
    ]
