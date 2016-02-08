# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0046_shopifyproduct_variants_map'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='register_hash',
            field=models.CharField(default=b'', max_length=50, blank=True),
        ),
    ]
