# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0032_auto_20151221_2012'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='shopifyproduct',
            name='original_data',
        ),
    ]
