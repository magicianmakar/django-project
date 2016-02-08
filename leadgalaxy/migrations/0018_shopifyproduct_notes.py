# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0017_auto_20151201_1444'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='notes',
            field=models.TextField(default=b''),
        ),
    ]
