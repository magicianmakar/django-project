# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0023_auto_20151212_1344'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyproduct',
            name='notes',
            field=models.TextField(default=b'', blank=True),
        ),
    ]
