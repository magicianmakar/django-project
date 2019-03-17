# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('woocommerce_core', '0006_auto_20170701_1153'),
    ]

    operations = [
        migrations.CreateModel(
            name='WooOrderTrack',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order_id', models.BigIntegerField()),
                ('line_id', models.BigIntegerField()),
                ('product_id', models.BigIntegerField()),
                ('woocommerce_status', models.CharField(default='', max_length=128, null=True, verbose_name='WooCommerce Fulfillment Status', blank=True)),
                ('source_id', models.BigIntegerField(default=0, verbose_name='Source Order ID')),
                ('source_status', models.CharField(default='', max_length=128, verbose_name='Source Order Status', blank=True)),
                ('source_tracking', models.CharField(default='', max_length=128, verbose_name='Source Tracking Number', blank=True)),
                ('source_status_details', models.CharField(max_length=512, null=True, verbose_name='Source Status Details', blank=True)),
                ('hidden', models.BooleanField(default=False)),
                ('seen', models.BooleanField(default=False, verbose_name='User viewed the changes')),
                ('auto_fulfilled', models.BooleanField(default=False, verbose_name='Automatically fulfilled')),
                ('check_count', models.IntegerField(default=0)),
                ('data', models.TextField(default='', blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Submission date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Last update')),
                ('status_updated_at', models.DateTimeField(auto_now_add=True, verbose_name='Last Status Update')),
                ('store', models.ForeignKey(to='woocommerce_core.WooStore', null=True, on_delete=django.db.models.deletion.CASCADE)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AlterIndexTogether(
            name='wooordertrack',
            index_together=set([('store', 'order_id', 'line_id')]),
        ),
    ]
