# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import json


def safe_int(val, default=0):
    try:
        return int(val)
    except:
        return default


def order_source_id(apps, schema_editor):
    ShopifyOrder = apps.get_model("leadgalaxy", "ShopifyOrder")

    print
    print '* Begin Shopify Order merging for {} Orders'.format(ShopifyOrder.objects.count())

    for order in ShopifyOrder.objects.all():
        if not order.source_id:
            order.source_id = safe_int(json.loads(order.data)['aliexpress']['order']['id'])
            order.save()


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0055_shopifyorder_source_id'),
    ]

    operations = [
        migrations.RunPython(order_source_id),
    ]
