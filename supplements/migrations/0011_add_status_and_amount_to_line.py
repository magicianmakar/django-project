# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-11-11 13:13
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0010_add_label_in_order_line'),
    ]

    operations = [
        migrations.AddField(
            model_name='plsorderline',
            name='amount',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='plsorderline',
            name='is_label_printed',
            field=models.BooleanField(default=False),
        ),
    ]
