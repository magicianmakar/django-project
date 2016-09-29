# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0118_shopifyproduct_mapping_config'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='hidden',
            field=models.BooleanField(default=False, verbose_name=b'Hidden from users'),
        ),
    ]
