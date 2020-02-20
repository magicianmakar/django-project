# -*- coding: utf-8 -*-
# Generated by Django 1.11.26 on 2020-02-07 07:47
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0028_auto_20200204_1405'),
    ]

    operations = [
        migrations.CreateModel(
            name='LabelSize',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=100)),
                ('height', models.DecimalField(decimal_places=2, max_digits=10)),
                ('width', models.DecimalField(decimal_places=2, max_digits=10)),
            ],
        ),
    ]