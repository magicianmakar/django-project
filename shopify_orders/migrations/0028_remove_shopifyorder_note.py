# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0027_auto_20170611_1426'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='shopifyorder',
            name='note',
        ),
    ]
