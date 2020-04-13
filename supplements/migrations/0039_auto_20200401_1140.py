# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2020-04-01 11:40
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0038_plsupplement_weight'),
    ]

    operations = [
        migrations.AddField(
            model_name='plsorder',
            name='shipping_price',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='shippinggroup',
            name='data',
            field=models.TextField(blank=True, help_text='Shipping rates (by weight) in the following Json format: <br> <pre><br>{<br>"shipping_cost_default":{DEFAULT_COST},<br>"shipping_rates":[<br>   {<br>      "weight_from":{FROM_LB},<br>      "weight_to":{TO_LB},<br>      "shipping_cost":{COST}<br>   },<br>   {<br>      "weight_from":{FROM_LB},<br>      "weight_to":{TO_LB},<br>      "shipping_cost":{COST}<br>   }<br>]<br>}</pre>', null=True),
        ),
    ]
