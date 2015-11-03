# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0007_shopifyboard'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyboard',
            name='products',
            field=models.ManyToManyField(to='leadgalaxy.ShopifyProduct', blank=True),
        ),
    ]
