# -*- coding: utf-8 -*-
# Generated by Django 1.11.26 on 2020-01-15 09:19
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0023_add_wholesale_price'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShippingGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.CharField(max_length=100, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('locations', models.TextField()),
                ('immutable', models.BooleanField(default=False)),
            ],
        ),
    ]
