# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0029_auto_20151218_1635'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='shopifyproduct',
            name='shopify_id',
        ),
        migrations.RemoveField(
            model_name='shopifyproductexport',
            name='product',
        ),
    ]
