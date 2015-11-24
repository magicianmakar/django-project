# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0010_auto_20151124_2042'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='original_data',
            field=models.TextField(default=b''),
        ),
    ]
