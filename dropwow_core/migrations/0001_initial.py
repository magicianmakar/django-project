# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0155_shopifyordertrack_source_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DropwowAccount',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('email', models.CharField(max_length=2048)),
                ('api_key', models.CharField(max_length=2048)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(related_name='dropwow_account', to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='DropwowOrderStatus',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('shopify_order_id', models.BigIntegerField()),
                ('shopify_line_id', models.BigIntegerField()),
                ('customer_address', models.TextField(null=True, blank=True)),
                ('order_id', models.CharField(max_length=255, null=True, verbose_name=b'Dropwow Order ID', blank=True)),
                ('status', models.CharField(max_length=255, null=True, blank=True)),
                ('tracking_number', models.CharField(max_length=255, null=True, blank=True)),
                ('error_message', models.CharField(max_length=255, null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, blank=True, to='leadgalaxy.ShopifyProduct', null=True)),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore', on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
    ]
