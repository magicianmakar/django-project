# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0113_auto_20160729_1227'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductSupplier',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('product_url', models.CharField(max_length=512, null=True, blank=True)),
                ('supplier_name', models.CharField(max_length=512, null=True, blank=True)),
                ('supplier_url', models.CharField(max_length=512, null=True, blank=True)),
                ('shipping_method', models.CharField(max_length=512, null=True, blank=True)),
                ('variants_map', models.TextField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='shopify_id',
            field=models.BigIntegerField(default=0, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='productsupplier',
            name='product',
            field=models.ForeignKey(to='leadgalaxy.ShopifyProduct', on_delete=django.db.models.deletion.CASCADE),
        ),
        migrations.AddField(
            model_name='productsupplier',
            name='store',
            field=models.ForeignKey(to='leadgalaxy.ShopifyStore', null=True, on_delete=django.db.models.deletion.CASCADE),
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='default_supplier',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, blank=True, to='leadgalaxy.ProductSupplier', null=True),
        ),
    ]
