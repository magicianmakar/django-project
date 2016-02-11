# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0060_shopifywebhook'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifywebhook',
            name='call_count',
            field=models.IntegerField(default=0),
        ),
    ]
