# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0030_auto_20151218_1717'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='original_dataz',
            field=models.BinaryField(default=None, null=True),
        ),
    ]
