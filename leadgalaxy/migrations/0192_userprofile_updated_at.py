# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-07-24 23:24
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0191_shopifystore_uninstall_reason'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, null=True),
        ),
    ]
