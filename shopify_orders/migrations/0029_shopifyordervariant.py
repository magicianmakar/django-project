# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0155_shopifyordertrack_source_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('shopify_orders', '0028_remove_shopifyorder_note'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyOrderVariant',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order_id', models.BigIntegerField(verbose_name=b'Shopify Order ID')),
                ('line_id', models.BigIntegerField(verbose_name=b'Shopify Line ID')),
                ('variant_id', models.BigIntegerField()),
                ('variant_title', models.TextField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('changed_by', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, null=True)),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore', on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
    ]
