# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-12-05 11:38
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('prints', '0008_product_description'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='customproduct',
            name='variants_images',
        ),
        migrations.RemoveField(
            model_name='customproduct',
            name='variants_info',
        ),
        migrations.RemoveField(
            model_name='customproduct',
            name='variants_sku',
        ),
    ]
