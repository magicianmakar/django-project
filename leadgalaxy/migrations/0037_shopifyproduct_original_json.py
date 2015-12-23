# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0036_shopifyproduct_parent_product'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='original_json',
            field=models.TextField(default=b'', blank=True),
        ),
    ]
