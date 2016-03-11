# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0085_auto_20160310_1513'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorder',
            name='auto_fulfilled',
            field=models.BooleanField(default=False, verbose_name=b'Automatically fulfilled'),
        ),
    ]
