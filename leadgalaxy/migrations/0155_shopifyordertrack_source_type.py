# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0154_adminevent_target_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyordertrack',
            name='source_type',
            field=models.CharField(max_length=512, null=True, verbose_name=b'Source Type', blank=True),
        ),
    ]
