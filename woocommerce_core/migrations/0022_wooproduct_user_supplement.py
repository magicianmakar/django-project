# -*- coding: utf-8 -*-
# Generated by Django 1.11.26 on 2020-02-12 15:06
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0027_plsorder_is_fulfilled'),
        ('woocommerce_core', '0021_wooordertrack_errors'),
    ]

    operations = [
        migrations.AddField(
            model_name='wooproduct',
            name='user_supplement',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='supplements.UserSupplement'),
        ),
    ]
