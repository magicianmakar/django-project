# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0022_sidebarlink_inherit_plan'),
    ]

    operations = [
        migrations.AddField(
            model_name='sidebarlink',
            name='store_type',
            field=models.CharField(default=b'default', max_length=50, choices=[(b'default', b'All Stores'), (b'shopify', b'Shopify'), (b'chq', b'CommerceHQ'), (b'woo', b'WooCommerce')]),
        ),
    ]
