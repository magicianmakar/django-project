# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CommerceHQBoard',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
            ],
            options={
                'verbose_name': 'CHQ Board',
                'verbose_name_plural': 'CHQ Boards',
            },
        ),
        migrations.CreateModel(
            name='CommerceHQOrderTrack',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order_id', models.BigIntegerField()),
                ('line_id', models.BigIntegerField()),
                ('commercehq_status', models.CharField(default=b'', max_length=128, null=True, verbose_name=b'CHQ Fulfillment Status', blank=True)),
                ('source_id', models.BigIntegerField(default=0, verbose_name=b'Source Order ID')),
                ('source_status', models.CharField(default=b'', max_length=128, verbose_name=b'Source Order Status', blank=True)),
                ('source_tracking', models.CharField(default=b'', max_length=128, verbose_name=b'Source Tracking Number', blank=True)),
                ('source_status_details', models.CharField(max_length=512, null=True, verbose_name=b'Source Status Details', blank=True)),
                ('hidden', models.BooleanField(default=False)),
                ('seen', models.BooleanField(default=False, verbose_name=b'User viewed the changes')),
                ('auto_fulfilled', models.BooleanField(default=False, verbose_name=b'Automatically fulfilled')),
                ('check_count', models.IntegerField(default=0)),
                ('data', models.TextField(default=b'', blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('status_updated_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Last Status Update')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CommerceHQProduct',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('data', models.TextField(default=b'{}', blank=True)),
                ('notes', models.TextField(null=True, blank=True)),
                ('title', models.CharField(max_length=300, db_index=True)),
                ('price', models.FloatField(db_index=True, null=True, blank=True)),
                ('product_type', models.CharField(max_length=300, db_index=True)),
                ('tags', models.TextField(default=b'', db_index=True, blank=True)),
                ('is_multi', models.BooleanField(default=False)),
                ('config', models.TextField(null=True, blank=True)),
                ('variants_map', models.TextField(default=b'', blank=True)),
                ('supplier_map', models.TextField(default=b'', null=True, blank=True)),
                ('shipping_map', models.TextField(default=b'', null=True, blank=True)),
                ('mapping_config', models.TextField(null=True, blank=True)),
                ('source_id', models.BigIntegerField(default=0, null=True, verbose_name=b'CommerceHQ Product ID', db_index=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'CHQ Product',
            },
        ),
        migrations.CreateModel(
            name='CommerceHQStore',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(default=b'', max_length=300, blank=True)),
                ('api_url', models.CharField(max_length=512)),
                ('api_key', models.CharField(max_length=300)),
                ('api_password', models.CharField(max_length=300)),
                ('is_active', models.BooleanField(default=True)),
                ('store_hash', models.CharField(default=b'', unique=True, max_length=50, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'CHQ Store',
            },
        ),
        migrations.CreateModel(
            name='CommerceHQSupplier',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('product_url', models.CharField(max_length=512, null=True, blank=True)),
                ('supplier_name', models.CharField(db_index=True, max_length=512, null=True, blank=True)),
                ('supplier_url', models.CharField(max_length=512, null=True, blank=True)),
                ('shipping_method', models.CharField(max_length=512, null=True, blank=True)),
                ('variants_map', models.TextField(null=True, blank=True)),
                ('is_default', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('product', models.ForeignKey(to='commercehq_core.CommerceHQProduct', on_delete=django.db.models.deletion.CASCADE)),
                ('store', models.ForeignKey(related_name='suppliers', to='commercehq_core.CommerceHQStore', on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='default_supplier',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, blank=True, to='commercehq_core.CommerceHQSupplier', null=True),
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='parent_product',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, verbose_name=b'Dupliacte of product', blank=True, to='commercehq_core.CommerceHQProduct', null=True),
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='store',
            field=models.ForeignKey(related_name='products', to='commercehq_core.CommerceHQStore', on_delete=django.db.models.deletion.CASCADE),
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE),
        ),
        migrations.AddField(
            model_name='commercehqordertrack',
            name='store',
            field=models.ForeignKey(to='commercehq_core.CommerceHQStore', null=True, on_delete=django.db.models.deletion.CASCADE),
        ),
        migrations.AddField(
            model_name='commercehqordertrack',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE),
        ),
        migrations.AddField(
            model_name='commercehqboard',
            name='products',
            field=models.ManyToManyField(to='commercehq_core.CommerceHQProduct', blank=True),
        ),
        migrations.AddField(
            model_name='commercehqboard',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE),
        ),
        migrations.AlterIndexTogether(
            name='commercehqordertrack',
            index_together=set([('store', 'order_id', 'line_id')]),
        ),
    ]
