# -*- coding: utf-8 -*-
# Generated by Django 1.11.26 on 2020-01-15 07:49
from __future__ import unicode_literals
import os
from django.conf import settings
from django.db import migrations
from django.utils.text import slugify
import simplejson as json
from django.db.models import Q


def fill_shipping_groups2(apps, schema_editor):
    ShippingGroup = apps.get_model('supplements', 'ShippingGroup')

    us_price = {
        "shipping_cost_default": 30,
        "shipping_rates": [
            {
                "weight_from": 0,
                "weight_to": 0.5625,
                "shipping_cost": 3.34
            },
            {
                "weight_from": 0.5625,
                "weight_to": 1,
                "shipping_cost": 5.28
            },
            {
                "weight_from": 1,
                "weight_to": 2,
                "shipping_cost": 8.41
            },
            {
                "weight_from": 2,
                "weight_to": 3,
                "shipping_cost": 9.73
            },
            {
                "weight_from": 3,
                "weight_to": 4,
                "shipping_cost": 11.01
            },
            {
                "weight_from": 4,
                "weight_to": 5,
                "shipping_cost": 12.12
            },
            {
                "weight_from": 5,
                "weight_to": 6,
                "shipping_cost": 13.53
            },
            {
                "weight_from": 6,
                "weight_to": 7,
                "shipping_cost": 15.21
            },
            {
                "weight_from": 7,
                "weight_to": 8,
                "shipping_cost": 16.81
            },
            {
                "weight_from": 8,
                "weight_to": 9,
                "shipping_cost": 18.01
            },
            {
                "weight_from": 9,
                "weight_to": 10,
                "shipping_cost": 19.67
            },
            {
                "weight_from": 10,
                "weight_to": 15,
                "shipping_cost": 24.75
            }

        ]
    }

    ShippingGroup.objects.filter(slug__iexact='US').update(
        data=json.dumps(us_price)
    )

    us_hawaii_price = {
        "shipping_cost_default": 50,
        "shipping_rates": [
            {
                "weight_from": 0,
                "weight_to": 0.5625,
                "shipping_cost": 3.67
            },
            {
                "weight_from": 0.5625,
                "weight_to": 1,
                "shipping_cost": 5.70
            },
            {
                "weight_from": 1,
                "weight_to": 2,
                "shipping_cost": 9.81
            },
            {
                "weight_from": 2,
                "weight_to": 3,
                "shipping_cost": 13.47
            },
            {
                "weight_from": 3,
                "weight_to": 4,
                "shipping_cost": 16.94
            },
            {
                "weight_from": 4,
                "weight_to": 5,
                "shipping_cost": 19.58
            },
            {
                "weight_from": 5,
                "weight_to": 6,
                "shipping_cost": 22.77
            },
            {
                "weight_from": 6,
                "weight_to": 7,
                "shipping_cost": 26.04
            },
            {
                "weight_from": 7,
                "weight_to": 8,
                "shipping_cost": 29.25
            },
            {
                "weight_from": 8,
                "weight_to": 9,
                "shipping_cost": 32.67
            },
            {
                "weight_from": 9,
                "weight_to": 10,
                "shipping_cost": 36.09
            },
            {
                "weight_from": 10,
                "weight_to": 15,
                "shipping_cost": 43.83
            }

        ]
    }

    ShippingGroup.objects.filter(Q(slug__iexact='us-hi') | Q(slug__iexact='us-ak')).update(
        data=json.dumps(us_hawaii_price)
    )


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0044_merge_20200413_1709'),
    ]

    operations = [
        migrations.RunPython(fill_shipping_groups2),
    ]
