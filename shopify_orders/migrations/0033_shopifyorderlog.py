# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0176_auto_20180220_1830'),
        ('shopify_orders', '0032_shopifysyncstatus_elastic'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyOrderLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order_id', models.BigIntegerField()),
                ('logs', models.TextField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore')),
            ],
        ),
    ]
