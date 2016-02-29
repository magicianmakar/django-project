# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0058_shopifyorder_store'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorder',
            name='hidden',
            field=models.BooleanField(default=False),
        ),
    ]
