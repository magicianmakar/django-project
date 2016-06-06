# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0105_auto_20160602_2357'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproductexport',
            name='product',
            field=models.ForeignKey(to='leadgalaxy.ShopifyProduct', null=True),
        ),
    ]
