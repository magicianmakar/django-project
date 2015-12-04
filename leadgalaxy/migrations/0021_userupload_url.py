# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0020_userupload'),
    ]

    operations = [
        migrations.AddField(
            model_name='userupload',
            name='url',
            field=models.CharField(default=b'', max_length=512, verbose_name=b'Upload file URL', blank=True),
        ),
    ]
