# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2020-03-31 15:44
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0036_add_supplement_mockup_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='shippinggroup',
            name='data',
            field=models.TextField(blank=True, null=True),
        ),
    ]
