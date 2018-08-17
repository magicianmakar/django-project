# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0041_userprofile_config'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyproduct',
            name='parent_product',
            field=models.ForeignKey(verbose_name=b'Dupliacte of product', blank=True, to='leadgalaxy.ShopifyProduct', null=True, on_delete=django.db.models.deletion.CASCADE),
        ),
    ]
