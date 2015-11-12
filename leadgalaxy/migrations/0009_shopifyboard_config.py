# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0008_auto_20151103_1754'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyboard',
            name='config',
            field=models.CharField(default=b'', max_length=512, blank=True),
        ),
    ]
