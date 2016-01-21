# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0045_shopifyproductimage_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='variants_map',
            field=models.TextField(default=b'', blank=True),
        ),
    ]
