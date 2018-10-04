# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-10-04 15:58
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0178_groupplan_payment_interval'),
        ('shopify_orders', '0035_auto_20181004_1546'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='shopifyorderlog',
            options={'ordering': ['-created_at']},
        ),
        migrations.AlterIndexTogether(
            name='shopifyorderlog',
            index_together=set([('store', 'order_id', 'created_at')]),
        ),
    ]
