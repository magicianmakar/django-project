# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2020-03-09 13:09
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0034_add_mockup_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='plsupplement',
            name='mockup_type',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='mockup_type', to='supplements.MockupType'),
        ),
    ]