# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0005_auto_20170624_1408'),
    ]

    operations = [
        migrations.AddField(
            model_name='wooproduct',
            name='parent_product',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, verbose_name=b'Duplicate of product', blank=True, to='woocommerce_core.WooProduct', null=True),
        ),
        migrations.AlterField(
            model_name='wooproduct',
            name='store',
            field=models.ForeignKey(related_name='products', to='woocommerce_core.WooStore', null=True),
        ),
        migrations.AlterField(
            model_name='woosupplier',
            name='store',
            field=models.ForeignKey(related_name='suppliers', to='woocommerce_core.WooStore', null=True),
        ),
    ]
