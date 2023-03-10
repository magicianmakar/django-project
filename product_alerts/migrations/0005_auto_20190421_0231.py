# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-04-21 02:31
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('groovekart_core', '0001_initial'),
        ('leadgalaxy', '0187_auto_20190423_0113'),
        ('commercehq_core', '0009_commercehqboard_favorite'),
        ('product_alerts', '0004_auto_20190123_1423'),
    ]

    operations = [
        migrations.AddField(
            model_name='productchange',
            name='gkart_product',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='groovekart_core.GrooveKartProduct'),
        ),
        migrations.AddField(
            model_name='productvariantpricehistory',
            name='gkart_product',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='groovekart_core.GrooveKartProduct'),
        ),
        migrations.AlterIndexTogether(
            name='productvariantpricehistory',
            index_together=set([('shopify_product', 'variant_id'), ('gkart_product', 'variant_id'), ('chq_product', 'variant_id')]),
        ),
    ]
