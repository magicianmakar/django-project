# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0009_shopifyboard_config'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='accesstoken',
            options={'ordering': ['-created_at']},
        ),
        migrations.AlterModelOptions(
            name='shopifyboard',
            options={'ordering': ['title']},
        ),
        migrations.AlterModelOptions(
            name='shopifyproduct',
            options={'ordering': ['-created_at']},
        ),
        migrations.AlterModelOptions(
            name='shopifystore',
            options={'ordering': ['-created_at']},
        ),
    ]
