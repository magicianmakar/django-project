# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0015_shopifyorder_items_count'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyorder',
            name='store',
            field=models.ForeignKey(to='leadgalaxy.ShopifyStore'),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL),
        ),
    ]
