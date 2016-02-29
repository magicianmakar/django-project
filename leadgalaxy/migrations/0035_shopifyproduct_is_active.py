# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0034_auto_20151221_2016'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
