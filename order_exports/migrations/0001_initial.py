# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0135_auto_20170117_2158'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderExport',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('schedule', models.TimeField(null=True, blank=True)),
                ('receiver', models.TextField(null=True, blank=True)),
                ('description', models.CharField(default=b'', max_length=255)),
                ('url', models.CharField(default=b'', max_length=512, blank=True)),
                ('sample_url', models.CharField(default=b'', max_length=512, blank=True)),
                ('since_id', models.CharField(max_length=100, null=True)),
                ('copy_me', models.BooleanField(default=False)),
                ('previous_day', models.BooleanField(default=True)),
                ('fields', models.TextField(default=b'[]', blank=True)),
                ('line_fields', models.TextField(default=b'[]', blank=True)),
                ('shipping_address', models.TextField(default=b'[]', blank=True)),
                ('progress', models.IntegerField(default=0, null=True, blank=True)),
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
                ('created_at_min', models.DateTimeField(null=True, blank=True)),
                ('created_at_max', models.DateTimeField(null=True, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='OrderExportLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('started_by', models.DateTimeField(auto_now_add=True)),
                ('finished_by', models.DateTimeField(null=True, blank=True)),
                ('successful', models.BooleanField(default=False)),
                ('csv_url', models.CharField(default=b'', max_length=512, blank=True)),
                ('type', models.CharField(default=b'sample', max_length=100, choices=[(b'sample', b'Sample file'), (b'complete', b'Complete file')])),
                ('order_export', models.ForeignKey(related_name='logs', to='order_exports.OrderExport', on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='OrderExportQuery',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('code', models.CharField(max_length=50, null=True, blank=True)),
                ('params', models.TextField(default=b'')),
                ('count', models.IntegerField(default=0)),
                ('order_export', models.ForeignKey(related_name='queries', to='order_exports.OrderExport', on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.CreateModel(
            name='OrderExportVendor',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('raw_password', models.CharField(max_length=255, null=True, blank=True)),
                ('owner', models.ForeignKey(related_name='vendors', to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
                ('user', models.OneToOneField(related_name='vendor', to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
        migrations.AddField(
            model_name='orderexport',
            name='filters',
            field=models.OneToOneField(to='order_exports.OrderExportFilter', on_delete=django.db.models.deletion.CASCADE),
        ),
        migrations.AddField(
            model_name='orderexport',
            name='store',
            field=models.ForeignKey(to='leadgalaxy.ShopifyStore', on_delete=django.db.models.deletion.CASCADE),
        ),
        migrations.AddField(
            model_name='orderexport',
            name='vendor_user',
            field=models.ForeignKey(related_name='exports', on_delete=django.db.models.deletion.SET_NULL, blank=True, to='order_exports.OrderExportVendor', null=True),
        ),
    ]
