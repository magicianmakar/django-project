# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-03-21 09:45
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0186_groupplanchangelog'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='dashboard_description',
            field=models.CharField(blank=True, max_length=512, null=True, verbose_name='Plan description on dashboard page'),
        ),
    ]