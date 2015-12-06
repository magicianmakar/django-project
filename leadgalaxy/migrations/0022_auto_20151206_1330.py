# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0021_userupload_url'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='userupload',
            options={'ordering': ['-created_at']},
        ),
        migrations.AddField(
            model_name='shopifystore',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
