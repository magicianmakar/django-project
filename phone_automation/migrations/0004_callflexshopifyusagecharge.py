# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-07-05 11:52
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('phone_automation', '0003_auto_20190620_2057'),
    ]

    operations = [
        migrations.CreateModel(
            name='CallflexShopifyUsageCharge',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(blank=True, default='', max_length=50)),
                ('status', models.CharField(choices=[('not_paid', 'paid')], default='not_paid', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Last update')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='callflex_shopify_usage_charges', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('pk',),
            },
        ),
    ]
