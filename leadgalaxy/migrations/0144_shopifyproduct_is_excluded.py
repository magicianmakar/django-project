# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0143_auto_20170328_2304'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='is_excluded',
            field=models.NullBooleanField(),
        ),
    ]
