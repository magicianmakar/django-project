# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0098_auto_20160425_1459'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyproduct',
            name='store',
            field=models.ForeignKey(blank=True, to='leadgalaxy.ShopifyStore', null=True, on_delete=django.db.models.deletion.CASCADE),
        ),
    ]
