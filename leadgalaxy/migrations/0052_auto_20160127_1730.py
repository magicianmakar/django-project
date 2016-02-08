# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0051_shopifyorder'),
    ]

    operations = [
        migrations.RenameField(
            model_name='shopifyorder',
            old_name='variant_id',
            new_name='line_id',
        ),
    ]
