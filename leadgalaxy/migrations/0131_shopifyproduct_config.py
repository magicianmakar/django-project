# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0130_clippingmagic'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='config',
            field=models.TextField(null=True, blank=True),
        ),
    ]
