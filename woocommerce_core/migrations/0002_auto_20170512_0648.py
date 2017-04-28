# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('woocommerce_core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='WooProduct',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('data', models.TextField(default=b'{}', blank=True)),
                ('notes', models.TextField(null=True, blank=True)),
                ('title', models.CharField(db_index=True, max_length=300, blank=True)),
                ('price', models.FloatField(db_index=True, null=True, blank=True)),
                ('tags', models.TextField(default=b'', db_index=True, blank=True)),
                ('source_id', models.BigIntegerField(default=0, null=True, verbose_name=b'WooCommerce Product ID', db_index=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'WooCommerce Product',
            },
        ),
        migrations.CreateModel(
            name='WooSupplier',
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
                ('product', models.ForeignKey(to='woocommerce_core.WooProduct')),
                ('store', models.ForeignKey(related_name='suppliers', to='woocommerce_core.WooStore')),
            ],
        ),
        migrations.AddField(
            model_name='wooproduct',
            name='default_supplier',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, blank=True, to='woocommerce_core.WooSupplier', null=True),
        ),
        migrations.AddField(
            model_name='wooproduct',
            name='store',
            field=models.ForeignKey(related_name='products', to='woocommerce_core.WooStore'),
        ),
        migrations.AddField(
            model_name='wooproduct',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL),
        ),
    ]
