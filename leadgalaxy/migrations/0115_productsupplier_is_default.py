# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0114_auto_20160805_1844'),
    ]

    operations = [
        migrations.AddField(
            model_name='productsupplier',
            name='is_default',
            field=models.BooleanField(default=False),
        ),
    ]
