# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_revision', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productrevision',
            name='store',
            field=models.ForeignKey(blank=True, to='leadgalaxy.ShopifyStore', null=True),
        ),
    ]
