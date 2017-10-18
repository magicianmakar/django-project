# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0007_commercehqproduct_monitor_id'),
        ('product_alerts', '0003_auto_20171130_1758'),
    ]

    operations = [
        migrations.AddField(
            model_name='productchange',
            name='chq_product',
            field=models.ForeignKey(to='commercehq_core.CommerceHQProduct', null=True),
        ),
        migrations.AlterField(
            model_name='productchange',
            name='shopify_product',
            field=models.ForeignKey(to='leadgalaxy.ShopifyProduct', null=True),
        ),
    ]
