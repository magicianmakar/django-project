# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0071_auto_20160222_2229'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorder',
            name='seen',
            field=models.BooleanField(default=False, verbose_name=b'User viewed the changes'),
        ),
    ]
