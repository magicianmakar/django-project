# -*- coding: utf-8 -*-
# Generated by Django 1.11.26 on 2020-02-20 04:00
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0201_shopifyproduct_user_supplement'),
    ]

    operations = [
        migrations.AddField(
            model_name='dashboardvideo',
            name='store_type',
            field=models.CharField(choices=[('shopify', 'Shopify'), ('chq', 'CommerceHQ'), ('woo', 'WooCommerce'), ('gkart', 'GrooveKart'), ('bigcommerce', 'BigCommerce')], default='shopify', max_length=50),
        ),
    ]
