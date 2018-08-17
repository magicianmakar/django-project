# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0129_shopifyproduct_original_data_key'),
        ('shopify_orders', '0018_auto_20161110_0936'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyOrderShippingLine',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('shipping_line_id', models.BigIntegerField()),
                ('price', models.FloatField()),
                ('title', models.CharField(max_length=256, db_index=True)),
                ('code', models.CharField(max_length=256)),
                ('source', models.CharField(max_length=256)),
                ('phone', models.CharField(max_length=256, null=True, blank=True)),
                ('carrier_identifier', models.CharField(max_length=256, null=True, blank=True)),
                ('requested_fulfillment_service_id', models.CharField(max_length=256, null=True, blank=True)),
                ('order', models.ForeignKey(related_name='shipping_lines', to='shopify_orders.ShopifyOrder', on_delete=django.db.models.deletion.CASCADE)),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore', on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
    ]
