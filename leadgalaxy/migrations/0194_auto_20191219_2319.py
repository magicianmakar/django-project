# -*- coding: utf-8 -*-
# Generated by Django 1.11.26 on 2019-12-19 23:19
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0193_groupplan_free_plan'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserAddress',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, default='', max_length=100)),
                ('address_line1', models.CharField(blank=True, default='', max_length=255)),
                ('address_line2', models.CharField(blank=True, default='', max_length=255)),
                ('city', models.CharField(blank=True, default='', max_length=100)),
                ('state', models.CharField(blank=True, default='', max_length=100)),
                ('country', models.CharField(blank=True, default='', max_length=100)),
                ('zip_code', models.CharField(blank=True, default='', max_length=100)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='userprofile',
            name='address',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='leadgalaxy.UserAddress'),
        ),
    ]
