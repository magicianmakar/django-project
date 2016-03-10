# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0083_auto_20160309_1519'),
    ]

    operations = [
        migrations.AddField(
            model_name='planregistration',
            name='email',
            field=models.CharField(default=b'', max_length=120, blank=True),
        ),
    ]
