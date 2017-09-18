# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0155_shopifyordertrack_source_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyordertrack',
            name='errors',
            field=models.IntegerField(null=True, blank=True),
        ),
    ]
