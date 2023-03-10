# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2020-04-08 08:25
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0041_fill_shipping_group_data_20200406_1120'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shippinggroup',
            name='data',
            field=models.TextField(blank=True, help_text='Shipping rates (by weight) in the following Json format <pre>\n        {\n        "shipping_cost_default":{DEFAULT_COST},\n        "shipping_rates":\n                        [\n                            {\n                               "weight_from":{FROM_LB},\n                               "weight_to":{TO_LB},\n                               "shipping_cost":{COST}\n                            },\n                            {\n                               "weight_from":{FROM_LB},\n                               "weight_to":{TO_LB},\n                               "shipping_cost":{COST}\n                            }\n                        ]\n        }\n        </pre>', null=True),
        ),
    ]
