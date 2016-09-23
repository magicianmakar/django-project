# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0118_shopifyproduct_mapping_config'),
        ('shopify_orders', '0013_auto_20160910_1505'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorderline',
            name='track',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to='leadgalaxy.ShopifyOrderTrack', null=True),
        ),
    ]
