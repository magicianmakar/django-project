# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0035_shopifyproduct_is_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='parent_product',
            field=models.ForeignKey(verbose_name=b'Dupliacte of product', to='leadgalaxy.ShopifyProduct', null=True),
        ),
    ]
