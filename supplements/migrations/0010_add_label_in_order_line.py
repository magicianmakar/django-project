# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-11-07 10:37
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0009_upgrade_pls_to_product_common'),
    ]

    operations = [
        migrations.AddField(
            model_name='plsorderline',
            name='label',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to='supplements.UserSupplementLabel'),
        ),
    ]