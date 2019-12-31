# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-10-04 13:24
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('bigcommerce_core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BigCommerceOrderTrack',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_id', models.BigIntegerField()),
                ('line_id', models.BigIntegerField()),
                ('product_id', models.BigIntegerField()),
                ('bigcommerce_status', models.CharField(blank=True, default='', max_length=128, null=True, verbose_name='BigCommerce Fulfillment Status')),
                ('source_id', models.CharField(blank=True, db_index=True, default='', max_length=512, verbose_name='Source Order ID')),
                ('source_status', models.CharField(blank=True, default='', max_length=128, verbose_name='Source Order Status')),
                ('source_tracking', models.CharField(blank=True, default='', max_length=128, verbose_name='Source Tracking Number')),
                ('source_status_details', models.CharField(blank=True, max_length=512, null=True, verbose_name='Source Status Details')),
                ('source_type', models.CharField(blank=True, max_length=512, null=True, verbose_name='Source Type')),
                ('hidden', models.BooleanField(default=False)),
                ('seen', models.BooleanField(default=False, verbose_name='User viewed the changes')),
                ('auto_fulfilled', models.BooleanField(default=False, verbose_name='Automatically fulfilled')),
                ('check_count', models.IntegerField(default=0)),
                ('data', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Submission date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Last update')),
                ('status_updated_at', models.DateTimeField(auto_now_add=True, verbose_name='Last Status Update')),
                ('store', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='bigcommerce_core.BigCommerceStore')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'abstract': False,
            },
        ),
        migrations.AlterIndexTogether(
            name='bigcommerceordertrack',
            index_together=set([('store', 'order_id', 'line_id')]),
        ),
    ]
