# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0113_auto_20160729_1227'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderExport',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('schedule', models.TimeField()),
                ('receiver', models.EmailField(max_length=254)),
                ('description', models.CharField(default=b'', max_length=255)),
                ('url', models.CharField(default=b'', max_length=512, blank=True)),
                ('fields', models.TextField(default=b'[]', blank=True)),
                ('line_fields', models.TextField(default=b'[]', blank=True)),
                ('billing_address', models.TextField(default=b'[]', blank=True)),
                ('shipping_address', models.TextField(default=b'[]', blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='OrderExportFilter',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('vendor', models.CharField(default=b'', max_length=255)),
                ('status', models.CharField(default=b'', max_length=50, blank=True)),
                ('fulfillment_status', models.CharField(default=b'', max_length=50, blank=True)),
                ('financial_status', models.CharField(default=b'', max_length=50, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='OrderExportFilterDates',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at_min', models.DateTimeField(null=True, blank=True)),
                ('created_at_min_days', models.IntegerField(null=True, blank=True)),
                ('created_at_max', models.DateTimeField(null=True, blank=True)),
                ('created_at_max_days', models.IntegerField(null=True, blank=True)),
                ('processed_at_min', models.DateTimeField(null=True, blank=True)),
                ('processed_at_min_days', models.IntegerField(null=True, blank=True)),
                ('processed_at_max', models.DateTimeField(null=True, blank=True)),
                ('processed_at_max_days', models.IntegerField(null=True, blank=True)),
                ('updated_at_min', models.DateTimeField(null=True, blank=True)),
                ('updated_at_min_days', models.IntegerField(null=True, blank=True)),
                ('updated_at_max', models.DateTimeField(null=True, blank=True)),
                ('updated_at_max_days', models.IntegerField(null=True, blank=True)),
            ],
        ),
        migrations.AddField(
            model_name='orderexportfilter',
            name='dates',
            field=models.OneToOneField(null=True, default=None, to='order_exports.OrderExportFilterDates'),
        ),
        migrations.AddField(
            model_name='orderexport',
            name='filters',
            field=models.OneToOneField(to='order_exports.OrderExportFilter'),
        ),
        migrations.AddField(
            model_name='orderexport',
            name='store',
            field=models.ForeignKey(to='leadgalaxy.ShopifyStore'),
        ),
    ]
