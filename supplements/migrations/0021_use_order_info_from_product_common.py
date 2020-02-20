# -*- coding: utf-8 -*-
# Generated by Django 1.11.26 on 2020-01-03 10:51
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0020_auto_20191220_1754'),
    ]

    operations = [
        migrations.RenameField(
            model_name='plsorder',
            old_name='order_id',
            new_name='store_order_id',
        ),
        migrations.RenameField(
            model_name='plsorderline',
            old_name='order_id',
            new_name='store_order_id',
        ),
        migrations.AlterUniqueTogether(
            name='plsorderline',
            unique_together=set([('store_type', 'store_id', 'store_order_id', 'line_id')]),
        ),
    ]