# -*- coding: utf-8 -*-
# Generated by Django 1.11.26 on 2020-01-20 13:27
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_common', '0003_order_dry'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='is_fulfilled',
            field=models.BooleanField(default=False),
        ),
    ]
