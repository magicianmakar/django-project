# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0018_shopifyproduct_notes'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='default_plan',
            field=models.IntegerField(default=0, choices=[(0, b'No'), (1, b'Yes')]),
        ),
    ]
