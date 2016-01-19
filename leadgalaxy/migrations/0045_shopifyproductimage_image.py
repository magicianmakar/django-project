# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0044_shopifyproductimage'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproductimage',
            name='image',
            field=models.CharField(default=b'', max_length=512, blank=True),
        ),
    ]
